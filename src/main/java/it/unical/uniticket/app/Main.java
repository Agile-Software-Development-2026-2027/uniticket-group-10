package it.unical.uniticket.app;

import it.unical.uniticket.routing.RoutingDecision;
import it.unical.uniticket.llm.LlmClient;
import it.unical.uniticket.llm.EmbeddingClient;
import it.unical.uniticket.llm.OllamaEmbeddingClient;
import it.unical.uniticket.llm.OllamaLlmClient;
import it.unical.uniticket.rag.UniTicketRagEngine;
import it.unical.uniticket.rag.UniTicketRagEngine.ScoredCategory;
import it.unical.uniticket.routing.TicketRouter;

import java.io.File;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.Scanner;

public class Main {

    private static final String OLLAMA_MODEL = "qwen2.5:3b";
    private static final String OLLAMA_BASE_URL = "http://localhost:11434";
    private static final String EMBEDDING_MODEL = "bge-m3";
    private static final int MAX_TURNS = 3;

    public static void main(String[] args) throws Exception {
        File catalogFile = new File("uniticket.json");
        if (!catalogFile.exists()) {
            System.err.println("❌ File uniticket.json non trovato in: " + catalogFile.getAbsolutePath());
            return;
        }

        LlmClient ollamaClient = new OllamaLlmClient(OLLAMA_BASE_URL + "/api/chat", OLLAMA_MODEL);
        EmbeddingClient embeddingClient = new OllamaEmbeddingClient(OLLAMA_BASE_URL, EMBEDDING_MODEL);
        System.out.println("⏳ Inizializzazione motore RAG (BM25 + embeddings)...");
        File embeddingCache = new File(".cache/uniticket-" + EMBEDDING_MODEL + "-embeddings.json");
        File taxonomyFile = new File("taxonomy.json");
        UniTicketRagEngine ragEngine = new UniTicketRagEngine(
                catalogFile, embeddingClient, true, true, embeddingCache, taxonomyFile);
        TicketRouter router = new TicketRouter(ragEngine, ollamaClient);

        Scanner scanner = new Scanner(System.in);
        System.out.println("==================================================================");
        System.out.println("🤖 UNITICKET AI AGENT - PROVA DRY-RUN (NESSUN INVIO REALE)");
        System.out.println("==================================================================");
        System.out.println("Esempi che puoi provare a scrivere:");
        System.out.println(" - \"Sono uno studente e non riesco ad entrare su Teams con la mail studenti\"");
        System.out.println(" - \"Il wifi eduroam_cr non funziona a Maisonnettes Blocco 4 stanza 12\"");
        System.out.println(" - \"Vorrei far riconoscere la mia certificazione Cambridge B2 a Ingegneria Informatica\"");
        System.out.print("\n💬 Descrivi il tuo problema: ");

        String initialUserMessage = scanner.nextLine().trim();
        if (initialUserMessage.isEmpty()) return;

        String cumulativeQuery = initialUserMessage;
        String clarification = "";
        List<ScoredCategory> previousCandidates = java.util.Collections.emptyList();
        Set<String> rejectedSlugs = new HashSet<>();
        RoutingDecision decision = null;

        for (int turn = 1; turn <= MAX_TURNS; turn++) {
            System.out.println("\n⏳ Ricerca ibrida (BM25 + embeddings + RRF)...");
            decision = turn == 1
                    ? router.route(cumulativeQuery, 5)
                    : router.route(clarification, 5, previousCandidates,
                    rejectedSlugs, cumulativeQuery);
            printDecision(decision);
            if (!"CLARIFY".equalsIgnoreCase(decision.action)) break;

            List<ScoredCategory> clarifyOptions = decision.clarifyOptions;
            int optionCount = Math.min(5, clarifyOptions.size());
            System.out.println("\n❓ Ho trovato più possibilità pertinenti:");
            for (int i = 0; i < optionCount; i++) {
                ScoredCategory candidate = clarifyOptions.get(i);
                System.out.printf("   %d) [%s] %s (%s)%n",
                        i + 1,
                        candidate.schema.structureName,
                        candidate.schema.categoryTitle,
                        candidate.schema.compositeSlug);
            }
            String question = decision.clarifyingQuestion;
            if (question == null || question.trim().isEmpty()) {
                question = "Indica il numero dell'opzione corretta oppure aggiungi qualche dettaglio.";
            }
            System.out.println(question);

            // Se l'utente seleziona uno dei candidati numerati, usa direttamente
            // quella scelta invece di lasciare che il modello la interpreti.
            int selectedIndex;
            while (true) {
                System.out.print("\n💬 Precisazione: ");
                clarification = scanner.hasNextLine() ? scanner.nextLine().trim() : "";
                if (clarification.isEmpty()) {
                    System.out.println("Nessuna precisazione fornita. Sessione annullata.");
                    return;
                }
                if ("0".equals(clarification)
                        || clarification.equalsIgnoreCase("nessuno")
                        || clarification.equalsIgnoreCase("nessuno di questi")) {
                    selectedIndex = -2;
                    break;
                }
                if (!clarification.matches("\\d{1,9}")) {
                    // La risposta è testo libero: verrà valutata nuovamente dal router.
                    selectedIndex = -1;
                    break;
                }
                selectedIndex = Integer.parseInt(clarification) - 1;
                if (selectedIndex >= 0 && selectedIndex < optionCount) {
                    break;
                }
                System.out.printf("Opzione non valida: scegli un numero tra 1 e %d, 0 per nessuno di questi, "
                                + "oppure descrivi meglio la richiesta.%n",
                        optionCount);
            }
            if (selectedIndex == -2) {
                for (ScoredCategory candidate : clarifyOptions) {
                    rejectedSlugs.add(candidate.schema.compositeSlug);
                }
                cumulativeQuery += "\nNessuna delle opzioni precedenti è pertinente.";
                previousCandidates = java.util.Collections.emptyList();
                clarification = "Nessuna delle opzioni precedenti è pertinente.";
                if (turn == MAX_TURNS) {
                    decision.action = "NONE";
                    decision.selectedCompositeSlug = "NONE";
                    decision.matchedSchema = null;
                    decision.confidence = 1.0;
                    decision.reasoning = "L'utente ha escluso tutti i candidati mostrati.";
                }
            } else if (selectedIndex >= 0) {
                ScoredCategory selected = clarifyOptions.get(selectedIndex);
                decision.selectedCompositeSlug = selected.schema.compositeSlug;
                decision.action = "SELECT";
                decision.confidence = 1.0;
                decision.reasoning = "Modulo selezionato direttamente dall'utente.";
                decision.matchedSchema = selected.schema;
            } else {
                cumulativeQuery += "\nPrecisazione: " + clarification;
                previousCandidates = decision.plausibleCandidates.isEmpty()
                        ? clarifyOptions : decision.plausibleCandidates;
            }
            if (!"CLARIFY".equalsIgnoreCase(decision.action)) {
                break;
            }
        }

        if ("NONE".equalsIgnoreCase(decision.selectedCompositeSlug) || decision.matchedSchema == null) {
            System.out.println("\n❌ Nessun modulo uniTicket compatibile con la tua richiesta.");
            return;
        }

        if (!decision.matchedSchema.accessible) {
            System.out.println("\n⚠️ Il modulo \"" + decision.matchedSchema.categoryTitle + "\" ("
                    + decision.matchedSchema.structureName + ") non è attualmente accessibile.");
            if (decision.matchedSchema.accessRestrictionReason != null
                    && !decision.matchedSchema.accessRestrictionReason.trim().isEmpty()) {
                System.out.println("   Motivo: " + decision.matchedSchema.accessRestrictionReason);
            }
            return;
        }

        System.out.println("\n==================================================================");
        System.out.println("✅ CLASSIFICAZIONE COMPLETATA");
        System.out.println("==================================================================");
        System.out.println("Struttura : " + decision.matchedSchema.structureName);
        System.out.println("Tipologia : " + decision.matchedSchema.categoryTitle);
        System.out.println("Stato     : attivo");
    }

    private static void printDecision(RoutingDecision decision) {
        for (int i = 0; i < decision.ragCandidates.size(); i++) {
            ScoredCategory sc = decision.ragCandidates.get(i);
            System.out.printf("   %d) [RRF: %.4f | attivo: %-5s] %s (%s)%n",
                    i + 1, sc.score, sc.schema.accessible,
                    sc.schema.categoryTitle, sc.schema.compositeSlug);
        }
        System.out.println("\n🎯 Decisione JEV Router:");
        System.out.println("   ├── Azione         : " + decision.action);
        System.out.println("   ├── Modulo scelto : " + decision.selectedCompositeSlug);
        System.out.println("   ├── Confidenza    : " + decision.confidence);
        System.out.println("   └── Motivazione   : " + decision.reasoning);
    }

}
