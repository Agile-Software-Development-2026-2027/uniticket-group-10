package it.unical.uniticket.routing;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import it.unical.uniticket.api.dto.CategoryFormSchema;
import it.unical.uniticket.forms.UniTicketAgentPipeline;
import it.unical.uniticket.llm.LlmClient;
import it.unical.uniticket.rag.UniTicketRagEngine;
import it.unical.uniticket.rag.UniTicketRagEngine.ScoredCategory;

import java.io.IOException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.stream.Collectors;

public class TicketRouter {
    private static final int MAX_NOTES_IN_PROMPT = 200;
    // Con RRF (k=60) un rapporto >= 0.95 corrisponde a candidati nelle prime posizioni
    // di entrambe le liste; chi è in cima a una sola lista resta sotto (~0.90).
    private static final double RANK_TIE_RATIO = 0.95;
    // Con bge-m3 i titoli normalizzati della stessa pratica superano 0.86, quelli
    // di pratiche diverse restano sotto 0.78.
    private static final double SAME_PRACTICE_SIMILARITY = 0.85;

    private final UniTicketRagEngine ragEngine;
    private final LlmClient llmClient;
    private final ObjectMapper mapper = new ObjectMapper();

    public TicketRouter(UniTicketRagEngine ragEngine, LlmClient llmClient) {
        this.ragEngine = ragEngine;
        this.llmClient = llmClient;
    }

    public UniTicketAgentPipeline.RoutingDecision route(String userRequest, int topK) {
        return route(userRequest, topK, Collections.emptyList());
    }

    public UniTicketAgentPipeline.RoutingDecision route(String userRequest, int topK,
                                                        List<ScoredCategory> previousCandidates) {
        if (isGenericEnrollmentRequest(userRequest)) {
            return genericEnrollmentClarification();
        }
        List<ScoredCategory> retrieved = ragEngine.searchTopKHybrid(userRequest, topK, false);
        List<ScoredCategory> candidates = mergeCandidates(previousCandidates, retrieved, topK);
        UniTicketAgentPipeline.RoutingDecision decision = new UniTicketAgentPipeline.RoutingDecision();
        decision.ragCandidates = candidates;
        if (candidates.isEmpty()) {
            decision.action = "NONE";
            decision.selectedCompositeSlug = "NONE";
            decision.confidence = 0.0;
            decision.reasoning = "Nessuna categoria compatibile trovata nel catalogo RAG.";
            return decision;
        }

        StringBuilder options = new StringBuilder();
        for (int i = 0; i < candidates.size(); i++) {
            CategoryFormSchema schema = candidates.get(i).schema;
            options.append(String.format("%d) ID: \"%s\" -> %s | Accessibile: %s%n",
                    i + 1, schema.compositeSlug, buildShortCandidateSummary(schema), schema.accessible));
        }

        String systemPrompt = "Sei il router delle richieste uniTicket dell'Università della Calabria.\n"
                + "Scegli una sola azione: SELECT, CLARIFY oppure NONE.\n"
                + "SELECT se un candidato è chiaramente pertinente.\n"
                + "CLARIFY se più candidati sono plausibili ma serve un dettaglio dell'utente.\n"
                + "NONE solo se nessun candidato è semanticamente collegato.\n"
                + "Non considerare pertinente un candidato solo perché contiene parole generiche come "
                + "\"problemi\", \"assistenza\", \"richiesta\" o \"iscrizione\"; verifica struttura e oggetto "
                + "specifico della pratica. Non usare moduli inattivi come scelta finale.\n"
                + "Non inventare dettagli non presenti nella richiesta, come anni accademici, corsi o "
                + "azioni già svolte dall'utente.\n"
                + "In plausibleSlugs elenca solo gli ID dei candidati realmente pertinenti alla richiesta.\n"
                + "Rispondi solo con JSON valido:\n"
                + "{\"action\":\"SELECT|CLARIFY|NONE\","
                + "\"selectedCompositeSlug\":\"<ID o NONE>\","
                + "\"plausibleSlugs\":[\"<ID>\"],"
                + "\"confidence\":0.0,"
                + "\"reasoning\":\"<motivazione in italiano>\","
                + "\"clarifyingQuestion\":\"<domanda se CLARIFY, altrimenti vuota>\"}";

        String userPrompt = "RICHIESTA UTENTE:\n\"" + userRequest
                + "\"\n\nCANDIDATI:\n" + options;
        List<String> plausibleSlugs = new ArrayList<>();
        try {
            JsonNode json = mapper.readTree(cleanJson(llmClient.generate(systemPrompt, userPrompt)));
            decision.action = json.path("action").asText("").trim().toUpperCase(Locale.ITALIAN);
            decision.selectedCompositeSlug = json.path("selectedCompositeSlug").asText("NONE").trim();
            decision.confidence = json.path("confidence").asDouble(0.8);
            decision.reasoning = json.path("reasoning").asText("");
            decision.clarifyingQuestion = json.path("clarifyingQuestion").asText("");
            for (JsonNode slug : json.path("plausibleSlugs")) {
                plausibleSlugs.add(slug.asText("").trim());
            }
        } catch (Exception e) {
            decision.action = "SELECT";
            decision.selectedCompositeSlug = candidates.get(0).schema.compositeSlug;
            decision.confidence = 0.6;
            decision.reasoning = "Fallback automatico sul Top-1 RAG (" + e.getMessage() + ")";
        }

        if (!Arrays.asList("SELECT", "CLARIFY", "NONE").contains(decision.action)) {
            decision.action = "NONE".equalsIgnoreCase(decision.selectedCompositeSlug)
                    ? "NONE" : "SELECT";
        }
        if ("NONE".equals(decision.action) && !previousCandidates.isEmpty()) {
            decision.action = "CLARIFY";
            decision.selectedCompositeSlug = "NONE";
            decision.matchedSchema = null;
            decision.clarifyOptions = previousCandidates.stream()
                    .filter(candidate -> candidate.schema.accessible)
                    .collect(Collectors.toList());
            decision.clarifyingQuestion = "La precisazione non identifica con certezza un modulo. "
                    + "Scegli un'opzione, indica 0 se nessuna è pertinente oppure aggiungi un altro dettaglio.";
            decision.reasoning = "La risposta non ha escluso in modo affidabile le opzioni già proposte.";
        }
        if ("CLARIFY".equals(decision.action)) {
            decision.selectedCompositeSlug = "NONE";
            decision.matchedSchema = null;
            List<ScoredCategory> accessible = candidates.stream()
                    .filter(candidate -> candidate.schema.accessible)
                    .collect(Collectors.toList());
            List<ScoredCategory> plausible = resolvePlausible(candidates, plausibleSlugs).stream()
                    .filter(candidate -> candidate.schema.accessible)
                    .collect(Collectors.toList());
            if (plausible.isEmpty()) {
                // L'LLM non ha indicato candidati validi: si propongono tutti quelli accessibili.
                decision.clarifyOptions = accessible;
            } else {
                // La stessa pratica offerta da altre strutture è plausibile quanto quella
                // indicata dall'LLM, anche se il modello non l'ha elencata.
                List<ScoredCategory> samePractice = samePracticeGroup(plausible.get(0), accessible);
                decision.clarifyOptions = accessible.stream()
                        .filter(candidate -> plausible.contains(candidate) || samePractice.contains(candidate))
                        .collect(Collectors.toList());
                if (samePractice.size() >= 2 && samePractice.containsAll(decision.clarifyOptions)) {
                    // L'unico dettaglio che distingue i candidati è la struttura, quindi la domanda è fissa.
                    decision.clarifyingQuestion = "La pratica è gestita da più strutture: a quale dipartimento "
                            + "o corso di laurea fai riferimento? Indica il numero dell'opzione.";
                }
            }
            if (decision.clarifyOptions.isEmpty()) {
                decision.action = "NONE";
                decision.reasoning = "Nessun modulo accessibile tra i candidati pertinenti.";
            } else if (decision.clarifyingQuestion == null || decision.clarifyingQuestion.trim().isEmpty()) {
                decision.clarifyingQuestion = "Quale dettaglio descrive meglio la tua richiesta?";
            }
        } else if (!"NONE".equalsIgnoreCase(decision.selectedCompositeSlug)) {
            decision.matchedSchema = ragEngine.findByCompositeSlug(decision.selectedCompositeSlug)
                    .orElse(candidates.get(0).schema);
        }
        return decision;
    }

    private List<ScoredCategory> mergeCandidates(List<ScoredCategory> previous,
                                                 List<ScoredCategory> retrieved, int topK) {
        List<ScoredCategory> merged = new ArrayList<>();
        Set<String> seen = new HashSet<>();
        for (ScoredCategory candidate : previous) {
            if (seen.add(candidate.schema.compositeSlug.toLowerCase(Locale.ROOT))) {
                merged.add(candidate);
            }
        }
        for (ScoredCategory candidate : retrieved) {
            if (seen.add(candidate.schema.compositeSlug.toLowerCase(Locale.ROOT))) {
                merged.add(candidate);
            }
        }
        return merged.stream().limit(topK).collect(Collectors.toList());
    }

    private boolean isGenericEnrollmentRequest(String userRequest) {
        if (userRequest == null) return false;
        String normalized = userRequest.toLowerCase(Locale.ITALIAN);
        boolean mentionsEnrollment = normalized.contains("immatricol")
                || normalized.contains("immatricolaz")
                || normalized.contains("immatricolarsi");
        boolean namesSpecificSystem = normalized.contains("esse3")
                || normalized.contains("esse 3")
                || normalized.contains("pagamento")
                || normalized.contains("tassa")
                || normalized.contains("document")
                || normalized.contains("corso");
        return mentionsEnrollment && !namesSpecificSystem;
    }

    private UniTicketAgentPipeline.RoutingDecision genericEnrollmentClarification() {
        UniTicketAgentPipeline.RoutingDecision decision = new UniTicketAgentPipeline.RoutingDecision();
        decision.action = "CLARIFY";
        decision.selectedCompositeSlug = "NONE";
        decision.confidence = 1.0;
        decision.reasoning = "La richiesta riguarda l'immatricolazione, ma non specifica la fase della procedura.";
        decision.clarifyingQuestion = "Il problema riguarda l'accesso a Esse3, un errore durante la procedura, "
                + "il pagamento, il caricamento dei documenti oppure la scelta del corso?";
        decision.clarifyOptions = new ArrayList<>();
        decision.ragCandidates = new ArrayList<>();
        return decision;
    }

    /**
     * Converte gli ID indicati dall'LLM nei corrispondenti candidati RAG, mantenendo
     * l'ordine del ranking. Accetta anche il numero del candidato, che i modelli
     * piccoli restituiscono spesso al posto dell'ID.
     */
    private List<ScoredCategory> resolvePlausible(List<ScoredCategory> candidates, List<String> plausibleSlugs) {
        Set<String> slugs = new HashSet<>();
        for (String slug : plausibleSlugs) {
            if (slug.matches("\\d+")) {
                int index = Integer.parseInt(slug) - 1;
                if (index >= 0 && index < candidates.size()) {
                    slugs.add(candidates.get(index).schema.compositeSlug.toLowerCase(Locale.ROOT));
                }
            } else {
                slugs.add(slug.toLowerCase(Locale.ROOT));
            }
        }
        double bestPlausibleScore = candidates.stream()
                .filter(candidate -> slugs.contains(candidate.schema.compositeSlug.toLowerCase(Locale.ROOT)))
                .mapToDouble(candidate -> candidate.score)
                .max().orElse(Double.MAX_VALUE);
        // Un candidato praticamente a pari merito nel ranking con uno ritenuto plausibile
        // non viene scartato: il modello piccolo tende a indicarne solo uno dei due.
        return candidates.stream()
                .filter(candidate -> slugs.contains(candidate.schema.compositeSlug.toLowerCase(Locale.ROOT))
                        || candidate.score >= bestPlausibleScore * RANK_TIE_RATIO)
                .collect(Collectors.toList());
    }

    /** Restituisce il candidato indicato e la stessa pratica offerta da altre strutture, una per struttura. */
    private List<ScoredCategory> samePracticeGroup(ScoredCategory anchor, List<ScoredCategory> pool) {
        List<ScoredCategory> group = new ArrayList<>();
        group.add(anchor);
        Set<String> structures = new HashSet<>();
        structures.add(anchor.schema.structureSlug);
        for (ScoredCategory candidate : pool) {
            if (candidate != anchor && !structures.contains(candidate.schema.structureSlug)
                    && ragEngine.titleSimilarity(anchor.schema, candidate.schema) >= SAME_PRACTICE_SIMILARITY) {
                group.add(candidate);
                structures.add(candidate.schema.structureSlug);
            }
        }
        return group;
    }

    private String buildShortCandidateSummary(CategoryFormSchema schema) {
        StringBuilder summary = new StringBuilder(schema.categoryTitle)
                .append(" | Struttura: ").append(schema.structureName);
        if (schema.categoryNotes != null && !schema.categoryNotes.trim().isEmpty()) {
            // Note troppo lunghe fanno perdere al modello i primi candidati dell'elenco.
            String notes = schema.categoryNotes.trim();
            if (notes.length() > MAX_NOTES_IN_PROMPT) {
                notes = notes.substring(0, MAX_NOTES_IN_PROMPT) + "…";
            }
            summary.append(" | Note: ").append(notes);
        }
        return summary.toString();
    }

    private String cleanJson(String raw) throws IOException {
        if (raw == null) {
            throw new IOException("Risposta LLM vuota.");
        }
        String cleaned = raw.trim();
        int first = cleaned.indexOf('{');
        int last = cleaned.lastIndexOf('}');
        if (first < 0 || last <= first) {
            throw new IOException("Risposta LLM non JSON.");
        }
        return cleaned.substring(first, last + 1);
    }
}
