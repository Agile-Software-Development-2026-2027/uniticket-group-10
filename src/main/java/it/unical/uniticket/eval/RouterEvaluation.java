package it.unical.uniticket.eval;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import it.unical.uniticket.routing.RoutingDecision;
import it.unical.uniticket.llm.OllamaEmbeddingClient;
import it.unical.uniticket.llm.OllamaLlmClient;
import it.unical.uniticket.rag.UniTicketRagEngine;
import it.unical.uniticket.rag.UniTicketRagEngine.ScoredCategory;
import it.unical.uniticket.routing.TicketRouter;

import java.io.File;
import java.util.ArrayList;
import java.util.List;

public final class RouterEvaluation {
    private static final int TOP_K = 5;
    private static final String URP = "urp__richieste-urp";

    private RouterEvaluation() {
    }

    public static void main(String[] args) throws Exception {
        File catalogFile = new File(args.length > 0 ? args[0] : "uniticket.json");
        File evaluationFile = new File(args.length > 1 ? args[1] : "eval/routing_eval.json");

        ObjectMapper mapper = new ObjectMapper();
        List<Case> cases = readCases(mapper, evaluationFile);
        UniTicketRagEngine rag = new UniTicketRagEngine(
                catalogFile,
                new OllamaEmbeddingClient("http://localhost:11434", "bge-m3"),
                true,
                true);
        TicketRouter router = new TicketRouter(
                rag,
                new OllamaLlmClient("http://localhost:11434/api/chat", "qwen2.5:3b"));

        int correct = 0;
        int strictSelect = 0;
        int singleIntentCases = 0;
        int clarifyCount = 0;
        int clarifyRecall = 0;
        int routableCases = 0;
        int noneCases = 0;
        int trueNegativeNone = 0;
        System.out.println("Valutazione router: qwen2.5:3b su BM25 + embeddings + RRF");
        System.out.println("Casi: " + cases.size());
        for (int i = 0; i < cases.size(); i++) {
            Case testCase = cases.get(i);
            RoutingDecision decision = router.route(testCase.query, TOP_K);
            boolean accepted = isAccepted(testCase, decision);
            if (testCase.expected.size() == 1) {
                singleIntentCases++;
                if ("SELECT".equalsIgnoreCase(decision.action)
                        && testCase.expected.contains(decision.selectedCompositeSlug)) {
                    strictSelect++;
                }
            }
            if ("CLARIFY".equalsIgnoreCase(decision.action)) {
                clarifyCount++;
                if (!testCase.expected.isEmpty()) {
                    routableCases++;
                    if (containsExpected(testCase, decision)) clarifyRecall++;
                }
            } else if (!testCase.expected.isEmpty()) {
                routableCases++;
            }
            if (testCase.expected.isEmpty()) {
                noneCases++;
                if ("NONE".equalsIgnoreCase(decision.action)
                        && "NONE".equalsIgnoreCase(decision.selectedCompositeSlug)) {
                    trueNegativeNone++;
                }
            }
            if (accepted) {
                correct++;
            } else {
                System.out.printf("%n[%d/%d] ERRATA%n  query: %s%n  attesi: %s%n"
                                + "  ottenuto: %s (%s)%n  motivazione: %s%n",
                        i + 1, cases.size(), testCase.query, testCase.expected,
                        decision.action, decision.selectedCompositeSlug, decision.reasoning);
            }
            System.out.printf("[%d/%d] %s -> %s (%s)%n",
                    i + 1, cases.size(), accepted ? "OK" : "NO",
                    decision.action, decision.selectedCompositeSlug);
        }
        System.out.printf("%nAccuratezza: %d/%d (%.1f%%)%n",
                correct, cases.size(), 100.0 * correct / cases.size());
        System.out.printf("Strict SELECT Accuracy: %d/%d (%.1f%%)%n",
                strictSelect, singleIntentCases, percentage(strictSelect, singleIntentCases));
        System.out.printf("Clarify Rate: %d/%d (%.1f%%)%n",
                clarifyCount, cases.size(), percentage(clarifyCount, cases.size()));
        System.out.printf("Clarify Recall: %d/%d (%.1f%%)%n",
                clarifyRecall, clarifyCount, percentage(clarifyRecall, clarifyCount));
        System.out.printf("Clarify Coverage Rate: %d/%d (%.1f%%)%n",
                clarifyRecall, routableCases, percentage(clarifyRecall, routableCases));
        System.out.printf("True Negative NONE Accuracy: %d/%d (%.1f%%)%n",
                trueNegativeNone, noneCases, percentage(trueNegativeNone, noneCases));
    }

    private static boolean isAccepted(Case testCase, RoutingDecision decision) {
        if (testCase.expected.isEmpty()) {
            return "NONE".equalsIgnoreCase(decision.action)
                    && "NONE".equalsIgnoreCase(decision.selectedCompositeSlug);
        }
        if (testCase.expected.contains(URP)
                && "NONE".equalsIgnoreCase(decision.action)) {
            return true;
        }
        if ("SELECT".equalsIgnoreCase(decision.action)) {
            return testCase.expected.contains(decision.selectedCompositeSlug);
        }
        if ("CLARIFY".equalsIgnoreCase(decision.action)) {
            return containsExpected(testCase, decision);
        }
        return false;
    }

    private static boolean containsExpected(Case testCase, RoutingDecision decision) {
        for (ScoredCategory option : decision.clarifyOptions) {
            if (testCase.expected.contains(option.schema.compositeSlug)) return true;
            for (it.unical.uniticket.api.dto.CategoryFormSchema variant : option.groupVariants) {
                if (testCase.expected.contains(variant.compositeSlug)) return true;
            }
        }
        return false;
    }

    private static double percentage(int numerator, int denominator) {
        return denominator == 0 ? 0.0 : 100.0 * numerator / denominator;
    }

    private static List<Case> readCases(ObjectMapper mapper, File file) throws Exception {
        List<Case> cases = new ArrayList<>();
        for (JsonNode node : mapper.readTree(file)) {
            List<String> expected = new ArrayList<>();
            for (JsonNode value : node.path("expected")) {
                String slug = value.asText();
                if (!"NONE".equals(slug)) {
                    expected.add(slug);
                }
            }
            cases.add(new Case(node.path("query").asText(), expected));
        }
        return cases;
    }

    private static final class Case {
        private final String query;
        private final List<String> expected;

        private Case(String query, List<String> expected) {
            this.query = query;
            this.expected = expected;
        }
    }
}
