package it.unical.uniticket.eval;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import it.unical.uniticket.llm.EmbeddingClient;
import it.unical.uniticket.llm.OllamaEmbeddingClient;
import it.unical.uniticket.rag.UniTicketRagEngine;
import it.unical.uniticket.rag.UniTicketRagEngine.ScoredCategory;

import java.io.File;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * Valuta il recall del retrieval BM25 sulle richieste annotate in eval/routing_eval.json.
 *
 * <p>Il runner non invoca il router LLM: misura soltanto se almeno un modulo atteso
 * compare nei primi K risultati. I casi annotati con NONE vengono riportati
 * separatamente perché non hanno un modulo atteso da cercare nel ranking.</p>
 */
public final class RoutingEvaluation {

    private static final int TOP_K = 5;

    private RoutingEvaluation() {
    }

    public static void main(String[] args) throws Exception {
        File catalogFile = new File(args.length > 0 ? args[0] : "uniticket.json");
        File evaluationFile = new File(args.length > 1 ? args[1] : "eval/routing_eval.json");
        boolean hybrid = args.length > 2 && "--hybrid".equalsIgnoreCase(args[2]);

        ObjectMapper mapper = new ObjectMapper();
        List<Case> cases = readCases(mapper, evaluationFile);
        EmbeddingClient embeddingClient = hybrid
                ? new OllamaEmbeddingClient("http://localhost:11434", "bge-m3")
                : null;
        Map<String, UniTicketRagEngine> engines = new LinkedHashMap<>();
        engines.put("stopword=on,sinonimi=on",
                new UniTicketRagEngine(catalogFile, embeddingClient, true, true));
        engines.put("stopword=on,sinonimi=off",
                new UniTicketRagEngine(catalogFile, embeddingClient, true, false));
        engines.put("stopword=off,sinonimi=on",
                new UniTicketRagEngine(catalogFile, embeddingClient, false, true));
        engines.put("stopword=off,sinonimi=off",
                new UniTicketRagEngine(catalogFile, embeddingClient, false, false));

        String mode = hybrid ? "BM25 + embeddings + RRF" : "BM25";
        System.out.println("Valutazione retrieval " + mode + ", Recall@" + TOP_K);
        System.out.println("Casi: " + cases.size());
        System.out.println();
        System.out.printf("%-29s %8s %8s %8s %8s%n",
                "Configurazione", "hit", "validi", "recall", "NONE");
        System.out.println("----------------------------------------------------------------");

        for (Map.Entry<String, UniTicketRagEngine> entry : engines.entrySet()) {
            int hits = 0;
            int validCases = 0;
            int noneTopResults = 0;
            for (Case testCase : cases) {
                List<ScoredCategory> results =
                        search(entry.getValue(), testCase.query, hybrid);
                if (testCase.expected.isEmpty()) {
                    if (results.isEmpty()) {
                        noneTopResults++;
                    }
                    continue;
                }
                validCases++;
                Set<String> resultSlugs = results.stream()
                        .map(result -> result.schema.compositeSlug)
                        .collect(Collectors.toSet());
                if (testCase.expected.stream().anyMatch(resultSlugs::contains)) {
                    hits++;
                }
            }
            double recall = validCases == 0 ? 0.0 : (double) hits / validCases;
            System.out.printf("%-29s %8d %8d %8.1f%% %8d%n",
                    entry.getKey(), hits, validCases, recall * 100.0, noneTopResults);
        }

        System.out.println();
        System.out.println("Dettaglio dei casi non recuperati (configurazione completa):");
        UniTicketRagEngine baseline = engines.get("stopword=on,sinonimi=on");
        for (Case testCase : cases) {
            if (testCase.expected.isEmpty()) {
                continue;
            }
            List<ScoredCategory> results = search(baseline, testCase.query, hybrid);
            Set<String> resultSlugs = results.stream()
                    .map(result -> result.schema.compositeSlug)
                    .collect(Collectors.toSet());
            if (testCase.expected.stream().noneMatch(resultSlugs::contains)) {
                System.out.println("- " + testCase.query);
                System.out.println("  attesi: " + testCase.expected);
                System.out.println("  trovati: " + resultSlugs);
            }
        }
    }

    private static List<ScoredCategory> search(UniTicketRagEngine engine, String query, boolean hybrid) {
        return hybrid
                ? engine.searchTopKHybrid(query, TOP_K, false)
                : engine.searchTopK(query, TOP_K, false);
    }

    private static List<Case> readCases(ObjectMapper mapper, File file) throws Exception {
        List<Case> cases = new ArrayList<>();
        for (JsonNode node : mapper.readTree(file)) {
            List<String> expected = new ArrayList<>();
            for (JsonNode value : node.path("expected")) {
                expected.add(value.asText());
            }
            expected.remove("NONE");
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
