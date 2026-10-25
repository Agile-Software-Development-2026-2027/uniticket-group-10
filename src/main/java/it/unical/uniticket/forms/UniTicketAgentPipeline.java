package it.unical.uniticket.forms;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import it.unical.uniticket.api.dto.CategoryFormSchema;
import it.unical.uniticket.api.dto.FieldSchema;
import it.unical.uniticket.api.dto.OptionItem;
import it.unical.uniticket.api.dto.TicketResult;
import it.unical.uniticket.llm.LlmClient;
import it.unical.uniticket.rag.OptionEmbeddingIndex;
import it.unical.uniticket.rag.OptionEmbeddingIndex.OptionMatch;
import it.unical.uniticket.rag.UniTicketRagEngine;
import it.unical.uniticket.rag.UniTicketRagEngine.ScoredCategory;
import it.unical.uniticket.routing.TicketRouter;

import java.io.File;
import java.io.IOException;
import java.util.*;
import java.util.stream.Collectors;

public class UniTicketAgentPipeline {
    private static final int OPTION_LIST_MAX_IN_PROMPT = 8;
    private static final int OPTION_CANDIDATES_FOR_LLM = 5;
    private static final double OPTION_EMBED_DIRECT_THRESHOLD = 0.85;

    private final UniTicketRagEngine ragEngine;
    private final LlmClient llmClient;
    private final TicketRouter ticketRouter;
    private final OptionEmbeddingIndex optionIndex;
    private final ObjectMapper mapper = new ObjectMapper();

    public UniTicketAgentPipeline(
            UniTicketRagEngine ragEngine,
            LlmClient llmClient) {
        this(ragEngine, llmClient, null);
    }

    public UniTicketAgentPipeline(
            UniTicketRagEngine ragEngine,
            LlmClient llmClient,
            OptionEmbeddingIndex optionIndex) {
        this.ragEngine = ragEngine;
        this.llmClient = llmClient;
        this.optionIndex = optionIndex;
        this.ticketRouter = new TicketRouter(ragEngine, llmClient);
    }

    // =========================================================================
    // STADIO 2: JEV ROUTER (Selezione deterministica tra i Top-K del RAG)
    // =========================================================================

    public static class RoutingDecision {
        public String action;
        public String selectedCompositeSlug;
        public double confidence;
        public String reasoning;
        public String clarifyingQuestion;
        public CategoryFormSchema matchedSchema;
        public List<ScoredCategory> ragCandidates;
        /** Candidati plausibili e accessibili da proporre all'utente in caso di CLARIFY. */
        public List<ScoredCategory> clarifyOptions = new ArrayList<>();
    }

    /**
     * Esegue:
     * 1) Ricerca RAG Top-K
     * 2) Costruzione dei Criteria JEV sui candidati
     * 3) Scelta vincolata del compositeSlug
     */
    public RoutingDecision routeUserRequest(String userRequest, int topK) {
        return ticketRouter.route(userRequest, topK);
    }

    /**
     * Verifica se i primi due risultati appartengono allo stesso ambito ma
     * rappresentano moduli diversi. In questo caso è preferibile chiedere
     * una precisazione invece di lasciare la scelta esclusivamente al modello.
     */
    public boolean needsRoutingClarification(RoutingDecision decision) {
        if (decision == null || decision.ragCandidates == null
                || decision.ragCandidates.size() < 2) {
            return false;
        }

        ScoredCategory first = decision.ragCandidates.get(0);
        ScoredCategory second = decision.ragCandidates.get(1);
        if (second.score < 0.02 || first.score / second.score >= 2.0) {
            return false;
        }

        String domain = (first.schema.categoryTitle + " " + first.schema.categoryNotes + " "
                + second.schema.categoryTitle + " " + second.schema.categoryNotes)
                .toLowerCase(Locale.ITALIAN);
        return domain.contains("sussid")
                || domain.contains("necessit")
                || domain.contains("bisogn")
                || domain.contains("disagi econom")
                || domain.contains("borsa");
    }

    public List<ScoredCategory> findAccessibleAlternatives(RoutingDecision decision) {
        if (decision == null || decision.matchedSchema == null
                || decision.matchedSchema.accessible
                || decision.ragCandidates == null) {
            return Collections.emptyList();
        }

        String selectedTitle = decision.matchedSchema.categoryTitle.toLowerCase(Locale.ITALIAN);
        return decision.ragCandidates.stream()
                .filter(candidate -> candidate.schema.accessible)
                .filter(candidate -> sameRequestArea(selectedTitle,
                        candidate.schema.categoryTitle.toLowerCase(Locale.ITALIAN)))
                .collect(Collectors.toList());
    }

    private boolean sameRequestArea(String selectedTitle, String candidateTitle) {
        if (selectedTitle.contains("piano di studi")) {
            return candidateTitle.contains("piano") && candidateTitle.contains("studi");
        }
        return false;
    }

    private boolean shouldPreferTopCandidate(
            String userRequest,
            List<ScoredCategory> candidates,
            String selectedCompositeSlug) {
        if (candidates.size() < 2
                || selectedCompositeSlug == null
                || candidates.get(0).schema.compositeSlug.equalsIgnoreCase(selectedCompositeSlug)) {
            return false;
        }

        double topScore = candidates.get(0).score;
        double secondScore = candidates.get(1).score;
        if (topScore < 20.0 || topScore < secondScore * 1.75) {
            return false;
        }

        String request = userRequest.toLowerCase(Locale.ITALIAN);
        String[] specificIndicators = {
                "debito", "debiti", "revoca", "restituz", "rateizz",
                "borsa", "part-time", "collaboraz", "centro residenziale"
        };
        for (String indicator : specificIndicators) {
            if (request.contains(indicator)) {
                return false;
            }
        }
        return true;
    }

    // =========================================================================
    // STADIO 3: SLOT-FILLING CONVERSAZIONALE & VALIDAZIONE CAMPI
    // =========================================================================

    public class FormFillingSession {
        private final CategoryFormSchema schema;
        private final Map<String, String> collectedTextData = new LinkedHashMap<>();
        private final Map<String, File> collectedFiles = new LinkedHashMap<>();
        private final List<String> conversationHistory = new ArrayList<>();

        public FormFillingSession(CategoryFormSchema schema) {
            this.schema = schema;
            // Pre-imposta tutte le checkbox obbligatorie di presa visione condizioni
            for (FieldSchema f : schema.fields) {
                if (f.autoFillCheckbox) {
                    collectedTextData.put(f.name, "on");
                }
            }
        }

        public CategoryFormSchema getSchema() {
            return schema;
        }

        public Map<String, String> getCollectedTextData() {
            return Collections.unmodifiableMap(collectedTextData);
        }

        public Map<String, File> getCollectedFiles() {
            return Collections.unmodifiableMap(collectedFiles);
        }

        /**
         * Restituisce la lista dei campi obbligatori ancora mancanti.
         */
        public List<FieldSchema> getMissingRequiredFields() {
            List<FieldSchema> missing = new ArrayList<>();
            for (FieldSchema f : schema.fields) {
                if (!f.askUser || !f.required) continue;

                if ("file".equalsIgnoreCase(f.type)) {
                    if (!collectedFiles.containsKey(f.name) || collectedFiles.get(f.name) == null) {
                        missing.add(f);
                    }
                } else {
                    String val = collectedTextData.get(f.name);
                    if (val == null || val.trim().isEmpty()) {
                        missing.add(f);
                    }
                }
            }
            return missing;
        }

        public boolean isReadyToSubmit() {
            return schema.accessible && getMissingRequiredFields().isEmpty();
        }

        /**
         * Processa un messaggio dell'utente, estrae tramite LLM i valori dei campi,
         * li valida contro le opzioni del form e restituisce la risposta da mostrare all'utente.
         */
        public String processUserMessage(String userMessage) {
            if (!schema.accessible) {
                return String.format(
                        "⚠️ La categoria selezionata (**%s** - %s) al momento non è compilabile.\n"
                                + "- **Motivo tecnico:** %s\n"
                                + "- **Note della struttura:** %s",
                        schema.categoryTitle,
                        schema.structureName,
                        schema.accessRestrictionReason,
                        schema.categoryNotes != null ? schema.categoryNotes : "Nessuna nota aggiuntiva."
                );
            }

            conversationHistory.add("Utente: " + userMessage);

            // 1. Chiede all'LLM di estrarre i campi dal messaggio dell'utente
            extractFieldsWithLlm(userMessage);

            // 2. Verifica se mancano ancora campi obbligatori
            List<FieldSchema> missing = getMissingRequiredFields();
            if (missing.isEmpty()) {
                return buildConfirmationSummary();
            }

            // 3. Genera la domanda per i campi mancanti (al massimo 3 alla volta per non sovraccaricare l'utente)
            return buildNextQuestionPrompt(missing);
        }

        /**
         * Permette di allegare programmaticamente un file per un campo di tipo "file".
         */
        public void attachFile(String fieldName, File file) {
            if (file != null && file.exists()) {
                collectedFiles.put(fieldName, file);
            }
        }

        /**
         * Invia effettivamente il ticket a uniTicket tramite UniTicketApiClient.
         */
        /*public TicketResult submit() throws IOException {
            if (!isReadyToSubmit()) {
                throw new IllegalStateException("Impossibile inviare il ticket: mancano ancora campi obbligatori: "
                        + getMissingRequiredFields().stream().map(f -> f.name).collect(Collectors.joining(", ")));
            }
            return apiClient.submitTicket(schema.structureSlug, schema.categorySlug, collectedTextData, collectedFiles);
        }*/

        private void extractFieldsWithLlm(String latestUserMessage) {
            StringBuilder schemaSpec = new StringBuilder();
            for (FieldSchema f : schema.fields) {
                if (!f.askUser) continue;
                schemaSpec.append(String.format("- name: \"%s\" | label: \"%s\" | type: %s | required: %s",
                        f.name, f.label, f.type, f.required));
                if (f.helpText != null && !f.helpText.isEmpty()) {
                    schemaSpec.append(" | help: \"").append(f.helpText).append("\"");
                }
                if (!f.options.isEmpty()) {
                    if (f.options.size() <= OPTION_LIST_MAX_IN_PROMPT) {
                        String allowed = f.options.stream()
                                .map(o -> "\"" + o.value + "\"")
                                .collect(Collectors.joining(", "));
                        schemaSpec.append(" | VALORI AMMESSI: [").append(allowed).append("]");
                    } else {
                        schemaSpec.append(" | (campo a scelta con molte opzioni: estrai il testo esatto scritto dall'utente)");
                    }
                }
                schemaSpec.append("\n");
            }

            String systemPrompt = "Sei un assistente che estrae i parametri per compilare il modulo uniTicket: \""
                    + schema.categoryTitle + "\".\n"
                    + "Regole:\n"
                    + "1. Estrai SOLO le informazioni esplicitamente fornite o chiaramente deducibili dal messaggio dell'utente.\n"
                    + "2. Usa anche i dati già raccolti e la conversazione precedente come contesto, senza sovrascrivere "
                    + "un dato già valido con un valore meno preciso.\n"
                    + "3. Per i campi 'ticket_subject' e 'ticket_description', se il contesto contiene una descrizione "
                    + "sufficiente del problema, genera automaticamente un oggetto sintetico e una descrizione chiara e formale. "
                    + "Se il contesto è insufficiente, non inventare un contenuto generico.\n"
                    + "4. Se un campo ha VALORI AMMESSI, usa ESATTAMENTE una stringa elencata. "
                    + "Per campi a scelta senza lista, riporta il testo esatto dell'utente.\n"
                    + "5. Per i campi di tipo 'file', se l'utente scrive un percorso file locale (es. /home/.../doc.pdf), estrai il path.\n"
                    + "6. Non inventare mai dati anagrafici (matricola, telefono, codice fiscale, date) non scritti dall'utente.\n"
                    + "Rispondi SOLO con un JSON piatto chiave-valore {\"<field_name>\": \"<valore>\"}.";

            String userPrompt = "SCHEMA CAMPI DEL MODULO:\n" + schemaSpec
                    + "\nDATI GIÀ RACCOLTI FINORA:\n" + collectedTextData
                    + "\nCONVERSAZIONE PRECEDENTE:\n" + conversationHistory
                    + "\nULTIMO MESSAGGIO UTENTE:\n\"" + latestUserMessage + "\"";

            String rawJson = llmClient.generate(systemPrompt, userPrompt);
            List<FieldSchema> ambiguousFields = new ArrayList<>();
            List<String> ambiguousValues = new ArrayList<>();
            try {
                JsonNode extracted = parseCleanJson(rawJson);
                if (extracted != null && extracted.isObject()) {
                    for (FieldSchema f : schema.fields) {
                        if (!f.askUser || !extracted.has(f.name)) continue;
                        JsonNode valNode = extracted.get(f.name);
                        if (valNode == null || valNode.isNull()) continue;

                        String candidateVal = valNode.asText().trim();
                        if (candidateVal.isEmpty() || "null".equalsIgnoreCase(candidateVal)) continue;

                        validateAndStoreField(f, candidateVal, ambiguousFields, ambiguousValues);
                    }
                }
            } catch (Exception ignored) {
                // Se l'LLM restituisce JSON malformato, mantiene i dati precedenti e ripropone la domanda
            }
            resolveAmbiguousFields(ambiguousFields, ambiguousValues);
        }

        private void validateAndStoreField(FieldSchema field, String rawValue,
                                           List<FieldSchema> ambiguous, List<String> rawValues) {
            if ("file".equalsIgnoreCase(field.type)) {
                File f = new File(rawValue);
                if (f.exists() && f.isFile()) {
                    collectedFiles.put(field.name, f);
                }
                return;
            }

            // Se il campo ha opzioni chiuse (select / radio), verifica o normalizza il valore
            if (!field.options.isEmpty()) {
                for (OptionItem opt : field.options) {
                    if ((opt.value != null && opt.value.equalsIgnoreCase(rawValue))
                            || (opt.label != null && opt.label.equalsIgnoreCase(rawValue))) {
                        collectedTextData.put(field.name, opt.value);
                        return;
                    }
                }
                // Match parziale univoco (es. utente scrive "Blocco 5" -> "Maisonnettes Blocco 5")
                List<OptionItem> partialMatches = field.options.stream()
                        .filter(o -> o.label != null
                                && o.label.toLowerCase(Locale.ITALIAN).contains(rawValue.toLowerCase(Locale.ITALIAN)))
                        .collect(Collectors.toList());
                if (partialMatches.size() == 1) {
                    collectedTextData.put(field.name, partialMatches.get(0).value);
                    return;
                }
                if (optionIndex != null) {
                    List<OptionMatch> top = optionIndex.findTopCandidates(rawValue, schema, field, 1);
                    if (!top.isEmpty() && top.get(0).score >= OPTION_EMBED_DIRECT_THRESHOLD) {
                        collectedTextData.put(field.name, top.get(0).option.value);
                        return;
                    }
                }
                ambiguous.add(field);
                rawValues.add(rawValue);
                return;
            }

            collectedTextData.put(field.name, rawValue);
        }

        private void resolveAmbiguousFields(List<FieldSchema> fields, List<String> rawValues) {
            if (fields.isEmpty()) return;
            StringBuilder prompt = new StringBuilder(
                    "Per ciascun campo scegli l'opzione più adatta tra i candidati. "
                            + "Se nessun candidato è adatto, usa NONE.\n\n");
            for (int i = 0; i < fields.size(); i++) {
                FieldSchema field = fields.get(i);
                List<OptionItem> candidates = optionIndex == null
                        ? field.options.stream().limit(OPTION_CANDIDATES_FOR_LLM).collect(Collectors.toList())
                        : optionIndex.findTopCandidates(rawValues.get(i), schema, field,
                                OPTION_CANDIDATES_FOR_LLM).stream()
                                .map(match -> match.option).collect(Collectors.toList());
                prompt.append("CAMPO: ").append(field.name)
                        .append("\nVALORE ESTRATTO: \"").append(rawValues.get(i)).append("\"\nCANDIDATI:\n");
                for (OptionItem candidate : candidates) {
                    prompt.append("- ").append(candidate.value).append("\n");
                }
                prompt.append("\n");
            }
            prompt.append("Rispondi SOLO con JSON: {\"<field_name>\": \"<value oppure NONE>\"}");
            try {
                JsonNode result = parseCleanJson(llmClient.generate(
                        "Sei un assistente che sceglie opzioni per un modulo.", prompt.toString()));
                if (result != null && result.isObject()) {
                    for (FieldSchema field : fields) {
                        String chosen = result.path(field.name).asText("").trim();
                        if (chosen.isEmpty() || "NONE".equalsIgnoreCase(chosen)) continue;
                        for (OptionItem option : field.options) {
                            if ((option.value != null && option.value.equalsIgnoreCase(chosen))
                                    || (option.label != null && option.label.equalsIgnoreCase(chosen))) {
                                collectedTextData.put(field.name, option.value);
                                break;
                            }
                        }
                    }
                }
            } catch (RuntimeException | IOException ignored) {
                // I campi irrisolti restano vuoti e vengono richiesti nel turno successivo.
            }
        }

        private String buildNextQuestionPrompt(List<FieldSchema> missingFields) {
            StringBuilder sb = new StringBuilder();
            sb.append("Per completare la richiesta **").append(schema.categoryTitle)
                    .append("** (").append(schema.structureName).append("), mi servono ancora questi dati obbligatori:\n\n");

            int limit = Math.min(missingFields.size(), 3);
            for (int i = 0; i < limit; i++) {
                FieldSchema f = missingFields.get(i);
                sb.append(String.format("%d. **%s**", i + 1, f.label));
                if ("file".equalsIgnoreCase(f.type)) {
                    sb.append(" *(indica il percorso del file da allegare)*");
                }
                if (f.helpText != null && !f.helpText.isEmpty()
                        && !f.helpText.startsWith("Il campo Oggetto")
                        && !f.helpText.startsWith("Il campo Descrizione")) {
                    sb.append(" — _").append(f.helpText).append("_");
                }
                if (!f.options.isEmpty()) {
                    String preview = f.options.stream()
                            .limit(10)
                            .map(o -> "`" + o.label + "`")
                            .collect(Collectors.joining(", "));
                    sb.append("\n   Opzioni: ").append(preview);
                    if (f.options.size() > 10) {
                        sb.append(" *(+" + (f.options.size() - 10) + " altre)*");
                    }
                }
                sb.append("\n");
            }
            return sb.toString();
        }

        private String buildConfirmationSummary() {
            StringBuilder sb = new StringBuilder();
            sb.append("✅ **Tutti i campi obbligatori sono stati compilati!**\n");
            sb.append("Ecco il riepilogo del ticket pronto per l'invio a **")
                    .append(schema.structureName).append("** → **").append(schema.categoryTitle).append("**:\n\n");

            for (FieldSchema f : schema.fields) {
                if (!f.askUser) continue;
                if ("file".equalsIgnoreCase(f.type)) {
                    File file = collectedFiles.get(f.name);
                    if (file != null) {
                        sb.append("- **").append(f.label).append(":** 📎 `").append(file.getName()).append("`\n");
                    }
                } else {
                    String val = collectedTextData.get(f.name);
                    if (val != null && !val.isEmpty()) {
                        sb.append("- **").append(f.label).append(":** ").append(val).append("\n");
                    }
                }
            }
            return sb.toString();
        }
    }

    public FormFillingSession startFormSession(CategoryFormSchema schema) {
        return new FormFillingSession(schema);
    }

    private JsonNode parseCleanJson(String rawLlmOutput) throws IOException {
        if (rawLlmOutput == null) return null;
        String cleaned = rawLlmOutput.trim();
        int firstBrace = cleaned.indexOf('{');
        int lastBrace = cleaned.lastIndexOf('}');
        if (firstBrace >= 0 && lastBrace > firstBrace) {
            cleaned = cleaned.substring(firstBrace, lastBrace + 1);
        }
        return mapper.readTree(cleaned);
    }
}
