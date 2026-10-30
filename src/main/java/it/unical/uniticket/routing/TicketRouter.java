package it.unical.uniticket.routing;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import it.unical.uniticket.api.dto.CategoryFormSchema;
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

    public RoutingDecision route(String userRequest, int topK) {
        return route(userRequest, topK, Collections.emptyList());
    }

    public RoutingDecision route(String userRequest, int topK,
                                 List<ScoredCategory> previousCandidates) {
        return route(userRequest, topK, previousCandidates, Collections.emptySet(), userRequest);
    }

    public RoutingDecision route(String userRequest, int topK,
                                 List<ScoredCategory> previousCandidates,
                                 Set<String> rejectedSlugs,
                                 String cumulativeQuery) {
        if (isGenericEnrollmentRequest(userRequest)) {
            return genericEnrollmentClarification();
        }
        if (!previousCandidates.isEmpty() && !containsNegation(userRequest)) {
            ScoredCategory confirmed = findTextConfirmedCandidate(userRequest, previousCandidates);
            if (confirmed != null) {
                ScoredCategory variant = findMentionedVariant(userRequest, confirmed);
                if (variant != null) {
                    return selectDecision(variant, "La precisazione dell'utente identifica la struttura "
                            + variant.schema.structureName + ".");
                }
                if (confirmed.groupVariants.size() > 1
                        && !mentionsStructure(userRequest, confirmed.groupVariants)) {
                    return clarifyVariants(confirmed);
                }
                return selectDecision(confirmed, "La precisazione dell'utente conferma il candidato "
                        + confirmed.schema.categoryTitle + ".");
            }
        }
        boolean clarificationTurn = !previousCandidates.isEmpty();
        int retrievalWindow = Math.max(topK * 3, 15);
        List<ScoredCategory> retrieved = ragEngine.searchTopKHybrid(
                cumulativeQuery == null || cumulativeQuery.trim().isEmpty()
                        ? userRequest : cumulativeQuery,
                retrievalWindow, false);
        List<ScoredCategory> filteredRetrieved = retrieved.stream()
                .filter(candidate -> !containsSlug(rejectedSlugs, candidate.schema.compositeSlug))
                .collect(Collectors.toList());
        boolean expansionTurn = clarificationTurn && hasNewTerms(userRequest, previousCandidates);
        List<ScoredCategory> candidates;
        if (!clarificationTurn) {
            // Primo turno: il pool arriva direttamente dal retrieval globale.
            candidates = filteredRetrieved.stream()
                    .filter(candidate -> candidate.schema.accessible)
                    .limit(topK)
                    .collect(Collectors.toList());
        } else if (expansionTurn) {
            // Nuovi termini nella precisazione: esplora nuovamente il catalogo.
            candidates = mergeCandidates(filteredRetrieved, previousCandidates, topK);
        } else {
            // Precisazione senza nuovi termini: restringi ai candidati già plausibili.
            candidates = previousCandidates.stream()
                    .filter(candidate -> !containsSlug(rejectedSlugs, candidate.schema.compositeSlug))
                    .filter(candidate -> candidate.schema.accessible)
                    .limit(topK)
                    .collect(Collectors.toList());
        }
        RoutingDecision decision = new RoutingDecision();
        decision.ragCandidates = candidates;
        decision.cumulativeQuery = cumulativeQuery;
        decision.rejectedSlugs.addAll(rejectedSlugs);
        if (candidates.isEmpty()) {
            decision.action = "NONE";
            decision.selectedCompositeSlug = "NONE";
            decision.confidence = 0.0;
            decision.reasoning = "Nessuna categoria compatibile trovata nel catalogo RAG.";
            return decision;
        }
        ScoredCategory bestRetrieved = filteredRetrieved.isEmpty()
                ? null : filteredRetrieved.get(0);
        if (!clarificationTurn && bestRetrieved != null
                && bestRetrieved.embeddingScore < 0.35
                && bestRetrieved.bm25Score == 0.0) {
            decision.action = "NONE";
            decision.selectedCompositeSlug = "NONE";
            decision.confidence = 1.0;
            decision.reasoning = "Nessun candidato raggiunge la soglia minima di rilevanza.";
            return decision;
        }
        ScoredCategory institutionalEmailCandidate = !clarificationTurn
                ? findInstitutionalEmailCandidate(userRequest, candidates)
                : null;
        if (institutionalEmailCandidate != null) {
            decision.action = "SELECT";
            decision.selectedCompositeSlug = institutionalEmailCandidate.schema.compositeSlug;
            decision.confidence = 0.95;
            decision.reasoning = "Il miglior candidato RAG identifica direttamente un problema "
                    + "di accesso o malfunzionamento dell'account email istituzionale.";
            decision.matchedSchema = institutionalEmailCandidate.schema;
            return decision;
        }
        if (!clarificationTurn && isGenericUniversityTaxRequest(userRequest)) {
            List<ScoredCategory> taxCandidates = filteredRetrieved.stream()
                    .filter(candidate -> candidate.schema.accessible)
                    .filter(this::isTaxCandidate)
                    .collect(Collectors.toList());
            if (!taxCandidates.isEmpty()) {
                taxCandidates = taxCandidates.stream().limit(topK).collect(Collectors.toList());
                decision.action = "CLARIFY";
                decision.selectedCompositeSlug = "NONE";
                decision.confidence = 1.0;
                decision.plausibleCandidates = new ArrayList<>(taxCandidates);
                decision.clarifyOptions = new ArrayList<>(taxCandidates);
                decision.clarifyingQuestion = "Che tipo di problema riguarda le tasse: un pagamento, "
                        + "una rata o un avviso PagoPA, una mora, un rimborso oppure la situazione "
                        + "della contribuzione?";
                decision.reasoning = "La richiesta riguarda genericamente le tasse e non contiene "
                        + "elementi sufficienti per scegliere una pratica specifica.";
                return decision;
            }
        }
        if (clarificationTurn && isGenericTaxSupportRequest(userRequest)) {
            ScoredCategory helpdeskTaxes = candidates.stream()
                    .filter(candidate -> candidate.schema.accessible)
                    .filter(candidate -> normalizeForMatch(candidate.schema.categoryTitle)
                            .contains("helpdesk situazione tasse"))
                    .findFirst()
                    .orElse(null);
            if (helpdeskTaxes != null) {
                decision.action = "SELECT";
                decision.selectedCompositeSlug = helpdeskTaxes.schema.compositeSlug;
                decision.confidence = 0.9;
                decision.reasoning = "La richiesta conferma un problema generico relativo al pagamento "
                        + "di una tassa; viene selezionato l'helpdesk per la situazione tasse.";
                decision.matchedSchema = helpdeskTaxes.schema;
                return decision;
            }
        }

        StringBuilder options = new StringBuilder();
        for (int i = 0; i < candidates.size(); i++) {
            CategoryFormSchema schema = candidates.get(i).schema;
            options.append(String.format("[%d] %s | Accessibile: %s%n",
            i + 1, buildShortCandidateSummary(schema), schema.accessible));
            if (candidates.get(i).groupVariants.size() > 1) {
                options.append("   Varianti della stessa pratica: ")
                        .append(candidates.get(i).groupVariants.stream()
                                .map(variant -> variant.structureName + " (" + variant.compositeSlug + ")")
                                .collect(Collectors.joining(", ")))
                        .append('\n');
            }
        }
        String taxonomyGuidance = ragEngine.clarificationGuidance(candidates);
        if (!taxonomyGuidance.isEmpty()) {
            options.append("\nGUIDA PER LA CHIARIFICAZIONE:\n")
                    .append(taxonomyGuidance).append('\n');
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
                + "Quando scegli CLARIFY, usa il discriminante più semplice tra quelli osservati "
                + "e formula una domanda in italiano. La guida tassonomica è solo un supporto, "
                + "non è una dichiarazione dell'utente.\n"
                + "Usa gli indici interi [1..K] dell'elenco. Per NONE usa selectedCandidateId = 0. "
                + "In plausibleCandidateIds elenca solo gli indici realmente pertinenti.\n"
                + "Rispondi solo con JSON valido:\n"
                + "{\"reasoning\":\"<motivazione in italiano>\","
                + "\"action\":\"SELECT|CLARIFY|NONE\","
                + "\"selectedCandidateId\":1,"
                + "\"plausibleCandidateIds\":[1],"
                + "\"confidence\":0.0,"
                + "\"clarifyingQuestion\":\"<domanda se CLARIFY, altrimenti vuota>\"}";

        String userPrompt = "RICHIESTA UTENTE:\n\"" + userRequest
                + "\"\n\nCANDIDATI:\n" + options;
        List<Integer> plausibleCandidateIds = new ArrayList<>();
        try {
            JsonNode json = mapper.readTree(cleanJson(llmClient.generate(
                    systemPrompt, userPrompt, buildRouterSchema(candidates))));
            decision.action = json.path("action").asText("").trim().toUpperCase(Locale.ITALIAN);
            int selectedId = json.path("selectedCandidateId").asInt(0);
            decision.selectedCompositeSlug = selectedId > 0 && selectedId <= candidates.size()
                    ? candidates.get(selectedId - 1).schema.compositeSlug : "NONE";
            decision.confidence = json.path("confidence").asDouble(0.8);
            decision.reasoning = json.path("reasoning").asText("");
            decision.clarifyingQuestion = json.path("clarifyingQuestion").asText("");
            for (JsonNode id : json.path("plausibleCandidateIds")) {
                if (id.isInt() && id.asInt() > 0 && id.asInt() <= candidates.size()) {
                    plausibleCandidateIds.add(id.asInt());
                }
            }
        } catch (Exception e) {
            decision.action = "CLARIFY";
            decision.selectedCompositeSlug = "NONE";
            decision.confidence = 0.0;
            decision.reasoning = "Risposta del router non utilizzabile: richiesta di conferma "
                    + "esplicita invece di una selezione automatica (" + e.getMessage() + ")";
            decision.clarifyOptions = new ArrayList<>(candidates);
            decision.plausibleCandidates = new ArrayList<>(candidates);
            decision.clarifyingQuestion = "Quale delle opzioni proposte descrive meglio la tua richiesta?";
        }

        if (!Arrays.asList("SELECT", "CLARIFY", "NONE").contains(decision.action)) {
            decision.action = "NONE".equalsIgnoreCase(decision.selectedCompositeSlug)
                    ? "NONE" : "SELECT";
        }
        if ("NONE".equals(decision.action)) {
            ScoredCategory confirmed = findStrongTextMatch(userRequest, candidates);
            if (confirmed != null) {
                decision.action = "SELECT";
                decision.selectedCompositeSlug = confirmed.schema.compositeSlug;
                decision.matchedSchema = confirmed.schema;
                decision.confidence = 0.9;
                decision.reasoning = "La richiesta contiene un termine specifico coerente con il modulo "
                        + confirmed.schema.categoryTitle + ".";
            } else if (previousCandidates.isEmpty() && shouldOfferNoneFallback(decision, candidates, userRequest)) {
                List<ScoredCategory> accessible = candidates.stream()
                        .filter(candidate -> candidate.schema.accessible)
                        .collect(Collectors.toList());
                if (!accessible.isEmpty()) {
                    decision.action = "CLARIFY";
                    decision.selectedCompositeSlug = "NONE";
                    decision.clarifyOptions = accessible;
                    decision.clarifyingQuestion = "Non riesco a confermare automaticamente un modulo. "
                            + "Scegli un'opzione, indica 0 se nessuna è pertinente oppure aggiungi un dettaglio.";
                    decision.reasoning = "Il modello ha restituito NONE, ma sono presenti candidati accessibili "
                            + "da verificare con l'utente.";
                }
            }
        }
        if ("NONE".equals(decision.action) && !previousCandidates.isEmpty()) {
            if (!hasNewTerms(userRequest, previousCandidates)) {
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
        }
        if ("CLARIFY".equals(decision.action)) {
            decision.selectedCompositeSlug = "NONE";
            decision.matchedSchema = null;
            List<ScoredCategory> accessible = candidates.stream()
                    .filter(candidate -> candidate.schema.accessible)
                    .collect(Collectors.toList());
            List<ScoredCategory> plausible = candidates.stream()
                    .filter(candidate -> plausibleCandidateIds.stream().anyMatch(id ->
                            candidates.get(id - 1).schema.compositeSlug
                                    .equalsIgnoreCase(candidate.schema.compositeSlug)))
                    .filter(candidate -> candidate.schema.accessible)
                    .collect(Collectors.toList());
            decision.plausibleCandidates = new ArrayList<>(plausible);
            if (plausible.isEmpty()) {
                // L'LLM non ha indicato candidati validi: si propongono tutti quelli accessibili.
                decision.clarifyOptions = accessible;
            } else {
                decision.clarifyOptions = clusterOptions(plausible.get(0), accessible);
                decision.clarifyOptions = includeCompetitiveCandidates(
                        decision.clarifyOptions, plausible, accessible);
                if (decision.clarifyOptions.size() > 1) {
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
        } else if ("SELECT".equals(decision.action)) {
            ScoredCategory selected = findCandidate(candidates, decision.selectedCompositeSlug);
            if (selected == null) {
                decision.action = "NONE";
                decision.selectedCompositeSlug = "NONE";
            } else if (selected.groupVariants.size() > 1
                    && !mentionsStructure(cumulativeQuery, selected.groupVariants)) {
                decision.action = "CLARIFY";
                decision.selectedCompositeSlug = "NONE";
                decision.clarifyOptions = variantOptions(selected, candidates);
                decision.clarifyingQuestion = "Per completare l'individuazione del modulo \""
                        + selected.schema.categoryTitle + "\", a quale dipartimento o struttura fai riferimento?";
            } else {
                decision.matchedSchema = selected.schema;
            }
        }
        return decision;
    }

    private boolean containsSlug(Set<String> slugs, String candidateSlug) {
        return slugs.stream().anyMatch(slug -> slug.equalsIgnoreCase(candidateSlug));
    }

    private boolean hasNewTerms(String query, List<ScoredCategory> previousCandidates) {
        Set<String> known = new HashSet<>();
        for (ScoredCategory candidate : previousCandidates) {
            known.addAll(significantTokens(candidate.schema.categoryTitle));
            known.addAll(significantTokens(candidate.schema.structureName));
        }
        for (String token : significantTokens(query)) {
            if (!known.contains(token)) return true;
        }
        return false;
    }

    private Set<String> significantTokens(String text) {
        Set<String> tokens = new HashSet<>();
        for (String token : normalizeForMatch(text).split(" ")) {
            if (token.length() >= 5) tokens.add(token);
        }
        return tokens;
    }

    private ScoredCategory findTextConfirmedCandidate(String userRequest,
                                                      List<ScoredCategory> previousCandidates) {
        String normalizedRequest = normalizeForMatch(userRequest);
        if (isBroadClarification(normalizedRequest)) {
            return null;
        }
        ScoredCategory best = null;
        int bestMatches = 0;
        int secondMatches = 0;
        for (ScoredCategory candidate : previousCandidates) {
            if (!candidate.schema.accessible) continue;
            String title = normalizeForMatch(candidate.schema.categoryTitle);
            int matches = 0;
            for (String token : title.split(" ")) {
                if (isDistinctiveCandidateToken(token)
                        && normalizedRequest.contains(token)) {
                    matches++;
                }
            }
            if (matches > bestMatches) {
                secondMatches = bestMatches;
                bestMatches = matches;
                best = candidate;
            } else if (matches > secondMatches) {
                secondMatches = matches;
            }
        }
        return bestMatches >= 2 && bestMatches > secondMatches ? best : null;
    }

    private ScoredCategory findMentionedVariant(String query, ScoredCategory cluster) {
        if (cluster.groupVariants.size() <= 1) return null;
        String normalized = normalizeForMatch(query);
        for (CategoryFormSchema variant : cluster.groupVariants) {
            String structure = normalizeForMatch(variant.structureName);
            String slug = normalizeForMatch(variant.structureSlug);
            if ((!structure.isEmpty() && normalized.contains(structure))
                    || (!slug.isEmpty() && normalized.contains(slug))) {
                return new ScoredCategory(variant, cluster.score);
            }
        }
        return null;
    }

    private RoutingDecision clarifyVariants(ScoredCategory cluster) {
        RoutingDecision decision = new RoutingDecision();
        decision.action = "CLARIFY";
        decision.selectedCompositeSlug = "NONE";
        decision.confidence = 1.0;
        decision.reasoning = "La pratica è stata identificata, ma manca la struttura competente.";
        decision.clarifyingQuestion = "A quale dipartimento o struttura fai riferimento?";
        decision.clarifyOptions = variantOptions(cluster, Collections.singletonList(cluster));
        decision.plausibleCandidates = new ArrayList<>(decision.clarifyOptions);
        decision.ragCandidates = new ArrayList<>(decision.clarifyOptions);
        return decision;
    }

    private boolean isBroadClarification(String normalizedRequest) {
        return normalizedRequest.contains("in generale")
                || normalizedRequest.contains("generico")
                || normalizedRequest.contains("genericamente")
                || normalizedRequest.contains("in modo generale")
                || normalizedRequest.contains("non so quale")
                || normalizedRequest.contains("non saprei");
    }

    private boolean isDistinctiveCandidateToken(String token) {
        if (token.length() < 5) return false;
        return !Arrays.asList(
                "richiesta", "richieste", "domanda", "domande",
                "problema", "problemi", "assistenza", "servizio",
                "universita", "università", "studente", "studenti",
                "modulo", "segnalazione", "informatico", "informatici"
        ).contains(token);
    }

    private boolean containsNegation(String text) {
        String normalized = normalizeForMatch(text);
        return Arrays.asList("non", "no", "invece", "escluso").stream()
                .anyMatch(token -> Arrays.asList(normalized.split(" ")).contains(token));
    }

    private RoutingDecision selectDecision(ScoredCategory candidate, String reasoning) {
        RoutingDecision decision = new RoutingDecision();
        decision.action = "SELECT";
        decision.selectedCompositeSlug = candidate.schema.compositeSlug;
        decision.confidence = 0.9;
        decision.reasoning = reasoning;
        decision.ragCandidates = new ArrayList<>();
        decision.matchedSchema = candidate.schema;
        return decision;
    }

    private ScoredCategory findStrongTextMatch(String userRequest, List<ScoredCategory> candidates) {
        String request = normalizeForMatch(userRequest);
        Set<String> specificTerms = new HashSet<>(Arrays.asList(
                "sito", "app", "wifi", "wireless", "teams", "esse3", "mensa",
                "erasmus", "ielts", "cambridge", "stato", "borsa", "tasse"));
        for (ScoredCategory candidate : candidates) {
            if (!candidate.schema.accessible) continue;
            String title = normalizeForMatch(candidate.schema.categoryTitle);
            boolean exactSpecificMatch = specificTerms.stream()
                    .anyMatch(term -> request.contains(term) && title.contains(term));
            if (exactSpecificMatch) return candidate;
        }
        return null;
    }

    private ScoredCategory findInstitutionalEmailCandidate(String userRequest,
                                                            List<ScoredCategory> candidates) {
        String query = normalizeForMatch(userRequest);
        boolean mentionsEmail = query.contains("email")
                || query.contains("mail")
                || query.contains("posta");
        boolean mentionsProblem = query.contains("problem")
                || query.contains("difficolt")
                || query.contains("access")
                || query.contains("acced")
                || query.contains("login")
                || query.contains("entra")
                || query.contains("credenzial")
                || query.contains("password")
                || query.contains("funzion");
        if (!mentionsEmail || !mentionsProblem) return null;

        return candidates.stream()
                .filter(candidate -> candidate.schema.accessible)
                .filter(candidate -> {
                    String title = normalizeForMatch(candidate.schema.categoryTitle);
                    String searchText = normalizeForMatch(candidate.schema.ragSearchText);
                    return title.contains("office365")
                            || title.contains("office 365")
                            || title.contains("servizimicrosoft")
                            || (title.contains("account") && searchText.contains("email"));
                })
                .findFirst()
                .orElse(null);
    }

    private boolean isGenericUniversityTaxRequest(String userRequest) {
        String query = normalizeForMatch(userRequest);
        boolean mentionsTax = query.contains("tass")
                || query.contains("contribuzion");
        boolean hasSpecificContext = query.contains("docente")
                || query.contains("pagopa")
                || query.contains("pagamento")
                || query.contains("rata")
                || query.contains("mora")
                || query.contains("rimborso")
                || query.contains("pergamena")
                || query.contains("laurea")
                || query.contains("bollo")
                || query.contains("esse3");
        return mentionsTax && !hasSpecificContext;
    }

    private boolean isGenericTaxSupportRequest(String userRequest) {
        String query = normalizeForMatch(userRequest);
        boolean mentionsTax = query.contains("tass")
                || query.contains("contribuzion")
                || query.contains("rata");
        boolean asksSupport = query.contains("support")
                || query.contains("aiut")
                || query.contains("problem")
                || query.contains("difficolt");
        boolean hasSpecificPractice = query.contains("docente")
                || query.contains("pagopa")
                || query.contains("mora")
                || query.contains("rimborso")
                || query.contains("pergamena")
                || query.contains("laurea");
        return mentionsTax && asksSupport && !hasSpecificPractice;
    }

    private boolean isTaxCandidate(ScoredCategory candidate) {
        String title = normalizeForMatch(candidate.schema.categoryTitle);
        String slug = normalizeForMatch(candidate.schema.categorySlug);
        boolean isTaxPractice = title.contains("tass")
                || title.contains("contribuzion")
                || slug.contains("tass")
                || slug.contains("contribuzion");
        boolean isUnrelatedPractice = title.contains("office365")
                || title.contains("office 365")
                || title.contains("recupero crediti")
                || title.contains("sussid")
                || title.contains("stato di necessita")
                || title.contains("stato di bisogno");
        return isTaxPractice && !isUnrelatedPractice;
    }

    private String normalizeForMatch(String text) {
        if (text == null) return "";
        return text.toLowerCase(Locale.ITALIAN)
                .replaceAll("[^a-z0-9àèéìòù ]", " ")
                .replaceAll("\\s+", " ")
                .trim();
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

    private ObjectNode buildRouterSchema(List<ScoredCategory> candidates) {
        ObjectNode schema = mapper.createObjectNode();
        schema.put("type", "object");
        ArrayNode required = schema.putArray("required");
        required.add("reasoning");
        required.add("action");
        required.add("selectedCandidateId");
        required.add("plausibleCandidateIds");
        required.add("confidence");
        required.add("clarifyingQuestion");
        schema.put("additionalProperties", false);

        ObjectNode properties = schema.putObject("properties");
        properties.putObject("reasoning").put("type", "string");
        ObjectNode action = properties.putObject("action");
        action.put("type", "string");
        action.putArray("enum").add("SELECT").add("CLARIFY").add("NONE");

        ArrayNode allowedIds = mapper.createArrayNode();
        allowedIds.add(0);
        for (int i = 1; i <= candidates.size(); i++) allowedIds.add(i);
        ObjectNode selected = properties.putObject("selectedCandidateId");
        selected.put("type", "integer");
        selected.set("enum", allowedIds);

        ObjectNode plausible = properties.putObject("plausibleCandidateIds");
        plausible.put("type", "array");
        ObjectNode items = plausible.putObject("items");
        items.put("type", "integer");
        ArrayNode plausibleIds = mapper.createArrayNode();
        for (int i = 1; i <= candidates.size(); i++) plausibleIds.add(i);
        items.set("enum", plausibleIds);

        properties.putObject("confidence").put("type", "number");
        properties.putObject("clarifyingQuestion").put("type", "string");
        return schema;
    }

    private List<ScoredCategory> includeCompetitiveCandidates(List<ScoredCategory> current,
                                                               List<ScoredCategory> plausible,
                                                               List<ScoredCategory> accessible) {
        List<ScoredCategory> result = new ArrayList<>(current);
        ScoredCategory best = plausible.get(0);
        for (ScoredCategory candidate : accessible) {
            if (result.contains(candidate) || plausible.contains(candidate)) continue;
            boolean closeEmbedding = candidate.embeddingScore >= best.embeddingScore - 0.05;
            boolean closeBm25 = candidate.bm25Score >= best.bm25Score * 0.85;
            if (closeEmbedding && closeBm25) result.add(candidate);
        }
        return result;
    }

    private ScoredCategory findCandidate(List<ScoredCategory> candidates, String slug) {
        if (slug == null) return null;
        return candidates.stream()
                .filter(candidate -> slug.equalsIgnoreCase(candidate.schema.compositeSlug))
                .findFirst()
                .orElse(null);
    }

    private List<ScoredCategory> clusterOptions(ScoredCategory candidate,
                                                List<ScoredCategory> accessible) {
        if (candidate.groupVariants.size() <= 1) {
            return new ArrayList<>(Collections.singletonList(candidate));
        }
        Set<String> slugs = candidate.groupVariants.stream()
                .map(variant -> variant.compositeSlug.toLowerCase(Locale.ROOT))
                .collect(Collectors.toSet());
        return accessible.stream()
                .filter(option -> slugs.contains(option.schema.compositeSlug.toLowerCase(Locale.ROOT)))
                .collect(Collectors.toList());
    }

    private List<ScoredCategory> variantOptions(ScoredCategory cluster,
                                                List<ScoredCategory> candidates) {
        List<ScoredCategory> options = new ArrayList<>();
        for (CategoryFormSchema variant : cluster.groupVariants) {
            ScoredCategory existing = findCandidate(candidates, variant.compositeSlug);
            if (existing != null) {
                options.add(existing);
            } else if (variant.accessible) {
                options.add(new ScoredCategory(variant, cluster.score));
            }
        }
        return options;
    }

    private boolean mentionsStructure(String query, List<CategoryFormSchema> variants) {
        String normalized = normalizeForMatch(query);
        return variants.stream().anyMatch(variant -> {
            String name = normalizeForMatch(variant.structureName);
            String slug = normalizeForMatch(variant.structureSlug);
            return (!name.isEmpty() && normalized.contains(name))
                    || (!slug.isEmpty() && normalized.contains(slug));
        });
    }

    private boolean shouldOfferNoneFallback(RoutingDecision decision,
                                             List<ScoredCategory> candidates,
                                             String query) {
        if (decision.confidence >= 0.85 && findStrongTextMatch(query, candidates) == null) {
            return false;
        }
        return candidates.stream().anyMatch(candidate ->
                candidate.embeddingScore >= 0.48 || candidate.bm25Score >= 0.35);
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

    private RoutingDecision genericEnrollmentClarification() {
        RoutingDecision decision = new RoutingDecision();
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

    private String buildShortCandidateSummary(CategoryFormSchema schema) {
        StringBuilder summary = new StringBuilder(schema.categoryTitle)
                .append(" | Struttura: ").append(schema.structureName);
        if (schema.routerCard != null && schema.routerCard.isObject()) {
            appendRouterCardValue(summary, schema.routerCard, "targetAudience", "Destinatari");
            appendRouterCardValue(summary, schema.routerCard, "scope", "Ambito");
        }
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

    private void appendRouterCardValue(StringBuilder summary, JsonNode card,
                                       String field, String label) {
        String value = card.path(field).asText("").trim();
        if (!value.isEmpty()) {
            if (value.length() > MAX_NOTES_IN_PROMPT) {
                value = value.substring(0, MAX_NOTES_IN_PROMPT) + "…";
            }
            summary.append(" | ").append(label).append(": ").append(value);
        }
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
