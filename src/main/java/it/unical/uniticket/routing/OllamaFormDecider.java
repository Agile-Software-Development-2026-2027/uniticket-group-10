package it.unical.uniticket.routing;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import it.unical.uniticket.access.UserProfile;
import it.unical.uniticket.api.dto.CategoryFormSchema;
import it.unical.uniticket.llm.LlmClient;
import it.unical.uniticket.rag.UniTicketRagEngine.ScoredCategory;

import java.io.IOException;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * Decisore basato su un modello linguistico generico.
 *
 * <p>Il prompt non menziona lo stato dei moduli: il modello giudica solo la pertinenza.
 * La confidenza autodichiarata viene ignorata perché non è calibrata.</p>
 */
public class OllamaFormDecider implements FormDecider {
    private static final int MAX_FIELD_LENGTH = 200;

    private static final String SYSTEM_PROMPT =
            "Sei il classificatore delle richieste uniTicket dell'Università della Calabria.\n"
            + "Ricevi la richiesta di un utente e un elenco numerato di moduli già vicini alla "
            + "richiesta. Devi indicare quale modulo gli serve.\n"
            + "Regole:\n"
            + "- match è il numero del modulo che risolve la richiesta. L'utente usa parole sue: "
            + "ragiona sul bisogno, non sulle parole uguali al titolo.\n"
            + "- Non scegliere un modulo solo perché condivide parole generiche come problema, "
            + "assistenza, richiesta o iscrizione.\n"
            + "- alternative elenca altri moduli solo se la richiesta non permette davvero di "
            + "distinguerli da match. Nella maggior parte dei casi resta vuoto.\n"
            + "- match è 0 solo se nessun modulo dell'elenco c'entra con la richiesta, ad esempio "
            + "per domande estranee all'università.\n"
            + "- Il profilo utente è un indizio: se la richiesta nomina una struttura, conta la "
            + "richiesta.\n"
            + "- Se ci sono alternative, domanda contiene una breve domanda in italiano che le "
            + "distingua, altrimenti è vuota.\n"
            + "Rispondi solo con JSON: {\"ragionamento\":\"<breve>\",\"match\":1,"
            + "\"alternative\":[],\"domanda\":\"\"}";

    private final LlmClient llmClient;
    private final ObjectMapper mapper = new ObjectMapper();

    public OllamaFormDecider(LlmClient llmClient) {
        this.llmClient = llmClient;
    }

    @Override
    public DeciderVerdict decide(String request, List<ScoredCategory> candidates, UserProfile profile) {
        try {
            String raw = llmClient.generate(SYSTEM_PROMPT, buildUserPrompt(request, candidates, profile),
                    buildSchema(candidates.size()));
            return parse(raw, candidates.size());
        } catch (RuntimeException | IOException e) {
            return DeciderVerdict.failed("Risposta del modello non utilizzabile: " + e.getMessage());
        }
    }

    private DeciderVerdict parse(String raw, int candidateCount) throws IOException {
        if (raw == null) throw new IOException("risposta vuota");
        int first = raw.indexOf('{');
        int last = raw.lastIndexOf('}');
        if (first < 0 || last <= first) throw new IOException("risposta non JSON");
        JsonNode json = mapper.readTree(raw.substring(first, last + 1));

        String reasoning = json.path("ragionamento").asText("");
        int match = json.path("match").asInt(0);
        if (match < 1 || match > candidateCount) return DeciderVerdict.noMatch(reasoning);

        Set<Integer> alternatives = new LinkedHashSet<>();
        for (JsonNode id : json.path("alternative")) {
            int value = id.asInt(0);
            if (value >= 1 && value <= candidateCount && value != match) alternatives.add(value - 1);
        }
        return DeciderVerdict.match(match - 1, new ArrayList<>(alternatives), null, reasoning,
                json.path("domanda").asText(""));
    }

    private String buildUserPrompt(String request, List<ScoredCategory> candidates, UserProfile profile) {
        StringBuilder prompt = new StringBuilder("RICHIESTA UTENTE:\n\"").append(request).append("\"\n");
        String profileText = describeProfile(profile);
        if (!profileText.isEmpty()) prompt.append("\nPROFILO UTENTE: ").append(profileText).append('\n');
        prompt.append("\nMODULI:\n");
        for (int i = 0; i < candidates.size(); i++) {
            prompt.append('[').append(i + 1).append("] ")
                    .append(describe(candidates.get(i))).append('\n');
        }
        return prompt.toString();
    }

    private String describeProfile(UserProfile profile) {
        String role = profile.role == UserProfile.Role.STAFF ? "personale universitario"
                : profile.role == UserProfile.Role.STUDENT ? "studente" : "";
        if (!profile.hasDepartment()) return role;
        return (role.isEmpty() ? "" : role + ", ") + "struttura " + profile.departmentSlug;
    }

    private String describe(ScoredCategory candidate) {
        CategoryFormSchema schema = candidate.schema;
        StringBuilder text = new StringBuilder(schema.categoryTitle);
        if (candidate.groupVariants.size() > 1) {
            text.append(" | Strutture: ").append(candidate.groupVariants.stream()
                    .map(variant -> variant.structureName)
                    .distinct()
                    .collect(Collectors.joining(", ")));
        } else {
            text.append(" | Struttura: ").append(schema.structureName);
        }
        if (schema.routerCard != null && schema.routerCard.isObject()) {
            appendField(text, "Destinatari", schema.routerCard.path("targetAudience").asText(""));
            appendField(text, "Ambito", schema.routerCard.path("scope").asText(""));
        }
        appendField(text, "Note", schema.categoryNotes);
        return text.toString();
    }

    private void appendField(StringBuilder text, String label, String value) {
        if (value == null || value.trim().isEmpty()) return;
        String trimmed = value.trim();
        if (trimmed.length() > MAX_FIELD_LENGTH) {
            trimmed = trimmed.substring(0, MAX_FIELD_LENGTH) + "…";
        }
        text.append(" | ").append(label).append(": ").append(trimmed);
    }

    private ObjectNode buildSchema(int candidateCount) {
        ObjectNode schema = mapper.createObjectNode();
        schema.put("type", "object");
        schema.put("additionalProperties", false);
        ArrayNode required = schema.putArray("required");
        required.add("ragionamento").add("match").add("alternative").add("domanda");

        ObjectNode properties = schema.putObject("properties");
        properties.putObject("ragionamento").put("type", "string");
        ObjectNode match = properties.putObject("match");
        match.put("type", "integer");
        ArrayNode matchIds = match.putArray("enum");
        ObjectNode alternatives = properties.putObject("alternative");
        alternatives.put("type", "array");
        ObjectNode items = alternatives.putObject("items");
        items.put("type", "integer");
        ArrayNode alternativeIds = items.putArray("enum");
        matchIds.add(0);
        for (int i = 1; i <= candidateCount; i++) {
            matchIds.add(i);
            alternativeIds.add(i);
        }
        properties.putObject("domanda").put("type", "string");
        return schema;
    }
}
