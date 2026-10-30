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
 * Valuta il recall del retrieval sulle richieste annotate in eval/routing_eval.json.
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
        File taxonomyFile = new File(args.length > 3 ? args[3] : "taxonomy.json");

        ObjectMapper mapper = new ObjectMapper();
        List<Case> cases = readCases(mapper, evaluationFile);
        EmbeddingClient embeddingClient = hybrid
                ? new OllamaEmbeddingClient("http://localhost:11434", "bge-m3")
                : null;
        Map<String, UniTicketRagEngine> engines = new LinkedHashMap<>();
        addEngines(engines, "catalog-only", catalogFile, embeddingClient, null);
        if (taxonomyFile.isFile()) {
            addEngines(engines, "taxonomy-aware", catalogFile, embeddingClient, taxonomyFile);
        } else {
            System.err.println("Tassonomia non trovata: " + taxonomyFile.getPath()
                    + ". Valuto solo il catalogo.");
        }

        String mode = hybrid ? "BM25 + embeddings + RRF" : "BM25";
        System.out.println("Valutazione retrieval " + mode + ", Recall@" + TOP_K);
        System.out.println("Casi: " + cases.size());
        System.out.println();
        System.out.printf("%-29s %8s %8s %8s %8s%n",
                "Configurazione", "hit", "validi", "recall", "NONE");
        System.out.println("----------------------------------------------------------------");

        Map<String, Integer> hitCounts = new LinkedHashMap<>();
        Map<String, Integer> validCounts = new LinkedHashMap<>();
        for (Map.Entry<String, UniTicketRagEngine> entry : engines.entrySet()) {
            int hits = 0;
            int validCases = 0;
            int noneTopResults = 0;
            int[] recallHits = new int[3];
            double reciprocalRank = 0.0;
            int rankedCases = 0;
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
                int firstExpectedRank = firstExpectedRank(results, testCase.expected);
                if (firstExpectedRank > 0) {
                    rankedCases++;
                    reciprocalRank += 1.0 / firstExpectedRank;
                    for (int cutoff = 1; cutoff <= 3; cutoff++) {
                        if (firstExpectedRank <= cutoff) recallHits[cutoff - 1]++;
                    }
                }
                Set<String> resultSlugs = results.stream()
                        .flatMap(result -> {
                            List<String> slugs = new ArrayList<>();
                            slugs.add(result.schema.compositeSlug);
                            result.groupVariants.forEach(variant -> slugs.add(variant.compositeSlug));
                            return slugs.stream();
                        })
                        .collect(Collectors.toSet());
                if (testCase.expected.stream().anyMatch(resultSlugs::contains)) {
                    hits++;
                }
            }
            double recall = validCases == 0 ? 0.0 : (double) hits / validCases;
            hitCounts.put(entry.getKey(), hits);
            validCounts.put(entry.getKey(), validCases);
            System.out.printf("%-29s %8d %8d %8.1f%% %8d%n",
                    entry.getKey(), hits, validCases, recall * 100.0, noneTopResults);
            System.out.printf("  Recall@1 %.1f%% | Recall@3 %.1f%% | MRR %.3f%n",
                    percentage(recallHits[0], validCases),
                    percentage(recallHits[2], validCases),
                    rankedCases == 0 ? 0.0 : reciprocalRank / validCases);
        }

        printTaxonomyDelta(cases, engines, hitCounts, validCounts, hybrid);
        System.out.println();
        System.out.println("Dettaglio dei casi non recuperati (configurazione completa):");
        UniTicketRagEngine baseline = engines.get("taxonomy-aware,stopword=on,sinonimi=on");
        if (baseline == null) {
            baseline = engines.get("catalog-only,stopword=on,sinonimi=on");
        }

        for (Case testCase : cases) {
            if (testCase.expected.isEmpty()) {
                continue;
            }

            List<ScoredCategory> results = search(baseline, testCase.query, hybrid);
            Set<String> resultSlugs = results.stream()
                    .flatMap(result -> {
                        List<String> slugs = new ArrayList<>();
                        slugs.add(result.schema.compositeSlug);
                        result.groupVariants.forEach(variant -> slugs.add(variant.compositeSlug));
                        return slugs.stream();
                    })
                    .collect(Collectors.toSet());
            if (testCase.expected.stream().noneMatch(resultSlugs::contains)) {
                System.out.println("- " + testCase.query);
                System.out.println("  attesi: " + testCase.expected);
                System.out.println("  trovati: " + resultSlugs);
            }
        }
    }

    private static int firstExpectedRank(List<ScoredCategory> results, List<String> expected) {
        for (int i = 0; i < results.size(); i++) {
            ScoredCategory result = results.get(i);
            if (expected.contains(result.schema.compositeSlug)
                    || result.groupVariants.stream()
                    .anyMatch(variant -> expected.contains(variant.compositeSlug))) {
                return i + 1;
            }
        }
        return 0;
    }

    private static double percentage(int numerator, int denominator) {
        return denominator == 0 ? 0.0 : 100.0 * numerator / denominator;
    }

    private static void printTaxonomyDelta(List<Case> cases,
                                           Map<String, UniTicketRagEngine> engines,
                                           Map<String, Integer> hitCounts,
                                           Map<String, Integer> validCounts,
                                           boolean hybrid) {
        String baselineKey = "catalog-only,stopword=on,sinonimi=on";
        String taxonomyKey = "taxonomy-aware,stopword=on,sinonimi=on";
        if (!engines.containsKey(taxonomyKey)) return;

        int improved = 0;
        int regressed = 0;
        int unchanged = 0;
        UniTicketRagEngine baseline = engines.get(baselineKey);
        UniTicketRagEngine taxonomy = engines.get(taxonomyKey);
        for (Case testCase : cases) {
            if (testCase.expected.isEmpty()) continue;
            boolean baselineHit = containsExpected(search(baseline, testCase.query, hybrid),
                    testCase.expected);
            boolean taxonomyHit = containsExpected(search(taxonomy, testCase.query, hybrid),
                    testCase.expected);
            if (taxonomyHit && !baselineHit) improved++;
            else if (baselineHit && !taxonomyHit) regressed++;
            else unchanged++;
        }

        int baselineHits = hitCounts.get(baselineKey);
        int taxonomyHits = hitCounts.get(taxonomyKey);
        int valid = validCounts.get(taxonomyKey);
        System.out.printf("%nDelta taxonomy-aware vs catalog-only (stopword=on,sinonimi=on): "
                        + "%+d hit, %+.1f punti percentuali%n",
                taxonomyHits - baselineHits,
                100.0 * (taxonomyHits - baselineHits) / valid);
        System.out.printf("Casi migliorati: %d | regressi: %d | invariati: %d%n",
                improved, regressed, unchanged);
    }

    private static boolean containsExpected(List<ScoredCategory> results, List<String> expected) {
        Set<String> resultSlugs = results.stream()
                .flatMap(result -> {
                    List<String> slugs = new ArrayList<>();
                    slugs.add(result.schema.compositeSlug);
                    result.groupVariants.forEach(variant -> slugs.add(variant.compositeSlug));
                    return slugs.stream();
                })
                .collect(Collectors.toSet());
        return expected.stream().anyMatch(resultSlugs::contains);
    }

    private static void addEngines(Map<String, UniTicketRagEngine> engines, String source,
                                   File catalogFile, EmbeddingClient embeddingClient,
                                   File taxonomyFile) throws Exception {
        engines.put(source + ",stopword=on,sinonimi=on",
                new UniTicketRagEngine(catalogFile, embeddingClient, true, true, null, taxonomyFile));
        engines.put(source + ",stopword=on,sinonimi=off",
                new UniTicketRagEngine(catalogFile, embeddingClient, true, false, null, taxonomyFile));
        engines.put(source + ",stopword=off,sinonimi=on",
                new UniTicketRagEngine(catalogFile, embeddingClient, false, true, null, taxonomyFile));
        engines.put(source + ",stopword=off,sinonimi=off",
                new UniTicketRagEngine(catalogFile, embeddingClient, false, false, null, taxonomyFile));
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
