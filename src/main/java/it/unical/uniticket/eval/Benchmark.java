package it.unical.uniticket.eval;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import it.unical.uniticket.access.UserProfile;
import it.unical.uniticket.api.dto.CategoryFormSchema;
import it.unical.uniticket.app.RouterFactory;
import it.unical.uniticket.rag.UniTicketRagEngine;
import it.unical.uniticket.rag.UniTicketRagEngine.ScoredCategory;
import it.unical.uniticket.routing.ConversationState;
import it.unical.uniticket.routing.FormRouter;
import it.unical.uniticket.routing.RoutingDecision;

import java.io.File;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * Valuta la pipeline completa, costruita come in produzione.
 *
 * <p>Uso: {@code Benchmark <casi.json> [--out esito.json] [--top-k N] [--no-phrases]
 * [--retrieval-only]}. Il turno di chiarimento è simulato con un utente che sceglie
 * l'opzione corretta quando compare.</p>
 *
 * <p>Un test congelato non va usato per mettere a punto regole o prompt, altrimenti smette di
 * misurare qualcosa. I due file {@code eval/frozen_test*.json} sono già stati consultati: la
 * prossima misura affidabile richiede casi nuovi.</p>
 */
public final class Benchmark {

    private Benchmark() {
    }

    public static void main(String[] args) throws Exception {
        String casesPath = args[0];
        String outPath = null;
        int topK = RouterFactory.DEFAULT_TOP_K;
        boolean usePhrases = true;
        boolean retrievalOnly = false;
        for (int i = 1; i < args.length; i++) {
            if ("--out".equals(args[i])) outPath = args[++i];
            else if ("--top-k".equals(args[i])) topK = Integer.parseInt(args[++i]);
            else if ("--no-phrases".equals(args[i])) usePhrases = false;
            else if ("--retrieval-only".equals(args[i])) retrievalOnly = true;
            else throw new IllegalArgumentException("Argomento sconosciuto: " + args[i]);
        }

        ObjectMapper mapper = new ObjectMapper();
        List<BenchmarkCase> cases = new ArrayList<>();
        for (JsonNode node : mapper.readTree(new File(casesPath))) cases.add(BenchmarkCase.from(node));

        UniTicketRagEngine engine = RouterFactory.createEngine(new File("uniticket.json"),
                usePhrases ? new File("form_phrases.json") : null);
        FormRouter router = RouterFactory.createRouter(engine, topK);

        Map<String, BenchmarkTally> byType = new LinkedHashMap<>();
        BenchmarkTally overall = new BenchmarkTally();
        ArrayNode rows = mapper.createArrayNode();
        for (BenchmarkCase testCase : cases) {
            ObjectNode row = rows.addObject();
            row.put("id", testCase.id).put("type", testCase.type).put("query", testCase.query);
            List<ScoredCategory> retrieved = engine.search(
                    testCase.query, topK, testCase.profile, Collections.emptySet());
            row.set("retrieved", toSlugs(mapper, retrieved));
            int rank = testCase.rankIn(retrieved);
            row.put("rank", rank);

            BenchmarkOutcome outcome;
            if (retrievalOnly) {
                outcome = BenchmarkOutcome.retrievalOnly(testCase, rank);
            } else {
                long start = System.currentTimeMillis();
                ConversationState state = new ConversationState(testCase.profile, testCase.query);
                RoutingDecision first = router.route(state);
                row.put("millis", System.currentTimeMillis() - start);
                row.put("action", first.action);
                row.put("selected", first.selectedCompositeSlug);
                row.put("closed", first.isClosedForm());
                row.put("searchedClosedForms", first.searchedClosedForms);
                row.put("reasoning", first.reasoning);
                row.set("options", toSlugs(mapper, first.clarifyOptions));
                outcome = BenchmarkOutcome.of(testCase, first, rank, router, state);
                row.put("outcome", outcome.label);
            }
            overall.add(outcome);
            byType.computeIfAbsent(testCase.type, type -> new BenchmarkTally()).add(outcome);
            System.out.printf("%-12s %-22s %s%n", testCase.id, outcome.label, testCase.query);
        }

        System.out.println();
        overall.print("TOTALE", retrievalOnly);
        for (Map.Entry<String, BenchmarkTally> entry : byType.entrySet()) {
            entry.getValue().print(entry.getKey(), retrievalOnly);
        }
        if (outPath != null) {
            mapper.writerWithDefaultPrettyPrinter().writeValue(new File(outPath), rows);
        }
    }

    private static ArrayNode toSlugs(ObjectMapper mapper, List<ScoredCategory> categories) {
        ArrayNode result = mapper.createArrayNode();
        for (ScoredCategory category : categories) {
            ObjectNode item = result.addObject();
            item.put("slug", category.schema.compositeSlug);
            item.put("bm25", category.bm25Score);
            item.put("embedding", category.embeddingScore);
            ArrayNode variants = item.putArray("variants");
            for (CategoryFormSchema variant : category.groupVariants) variants.add(variant.compositeSlug);
        }
        return result;
    }

    /** Un caso del benchmark. Un'attesa "NONE" insieme a dei moduli rende accettabile anche NONE. */
    static final class BenchmarkCase {
        final String id;
        final String type;
        final String query;
        final Set<String> expected;
        final boolean noneAcceptable;
        final UserProfile profile;

        BenchmarkCase(String id, String type, String query, Set<String> expected,
                      boolean noneAcceptable, UserProfile profile) {
            this.id = id;
            this.type = type;
            this.query = query;
            this.expected = expected;
            this.noneAcceptable = noneAcceptable;
            this.profile = profile;
        }

        static BenchmarkCase from(JsonNode node) {
            Set<String> expected = new LinkedHashSet<>();
            boolean none = false;
            for (JsonNode value : node.path("expected")) {
                if ("NONE".equals(value.asText())) none = true;
                else expected.add(value.asText());
            }
            String query = node.path("query").asText();
            String type = node.path("type").asText(expected.isEmpty() ? "off_topic"
                    : none ? "none_or_form" : "open");
            return new BenchmarkCase(node.path("id").asText(type), type, query, expected,
                    none, parseProfile(node.path("profile")));
        }

        private static UserProfile parseProfile(JsonNode profile) {
            if (profile.isMissingNode() || profile.isNull()) return UserProfile.unknown();
            String role = profile.path("role").asText("");
            String department = profile.path("department").isNull()
                    ? null : profile.path("department").asText(null);
            return UserProfile.of("staff".equals(role) ? UserProfile.Role.STAFF
                    : "student".equals(role) ? UserProfile.Role.STUDENT : UserProfile.Role.UNKNOWN, department);
        }

        boolean isOffTopic() {
            return expected.isEmpty();
        }

        boolean isScored() {
            return !isOffTopic() && !noneAcceptable;
        }

        boolean matches(ScoredCategory category) {
            return expected.contains(category.schema.compositeSlug)
                    || category.groupVariants.stream().anyMatch(v -> expected.contains(v.compositeSlug));
        }

        /** Posizione del primo modulo atteso (da 1), oppure 0 se assente. */
        int rankIn(List<ScoredCategory> retrieved) {
            for (int i = 0; i < retrieved.size(); i++) {
                if (matches(retrieved.get(i))) return i + 1;
            }
            return 0;
        }
    }

    /** Esito di un caso. */
    static final class BenchmarkOutcome {
        final BenchmarkCase testCase;
        final int rank;
        final String label;
        final String action;
        final int optionCount;

        private BenchmarkOutcome(BenchmarkCase testCase, int rank, String label, String action,
                                 int optionCount) {
            this.testCase = testCase;
            this.rank = rank;
            this.label = label;
            this.action = action;
            this.optionCount = optionCount;
        }

        static BenchmarkOutcome retrievalOnly(BenchmarkCase testCase, int rank) {
            return new BenchmarkOutcome(testCase, rank, "rank " + rank, "", 0);
        }

        static BenchmarkOutcome of(BenchmarkCase testCase, RoutingDecision first, int rank,
                                   FormRouter router, ConversationState state) {
            return new BenchmarkOutcome(testCase, rank, classify(testCase, first, router, state),
                    first.action, first.clarifyOptions.size());
        }

        private static String classify(BenchmarkCase testCase, RoutingDecision first,
                                       FormRouter router, ConversationState state) {
            if (testCase.isOffTopic()) {
                return RoutingDecision.NONE.equals(first.action) ? "offtopic_ok"
                        : RoutingDecision.SELECT.equals(first.action) ? "offtopic_selected" : "offtopic_clarified";
            }
            if (RoutingDecision.SELECT.equals(first.action)) {
                return testCase.expected.contains(first.selectedCompositeSlug) ? "right_first" : "wrong_select";
            }
            if (RoutingDecision.NONE.equals(first.action)) {
                return testCase.noneAcceptable ? "right_first" : "wrong_none";
            }
            for (ScoredCategory option : first.clarifyOptions) {
                if (!testCase.matches(option)) continue;
                RoutingDecision second = router.pick(option, state);
                if (RoutingDecision.SELECT.equals(second.action)) {
                    return testCase.expected.contains(second.selectedCompositeSlug)
                            ? "right_after_clarify" : "wrong_after_clarify";
                }
                // Scelta del dipartimento: un altro turno, l'utente indica la variante giusta.
                boolean reachable = second.clarifyOptions.stream().anyMatch(testCase::matches);
                return reachable ? "right_after_clarify" : "dead_end";
            }
            return "dead_end";
        }
    }

    /** Conteggi aggregati e relativa stampa, con intervalli di confidenza di Wilson. */
    static final class BenchmarkTally {
        private final List<BenchmarkOutcome> outcomes = new ArrayList<>();

        void add(BenchmarkOutcome outcome) {
            outcomes.add(outcome);
        }

        private long count(boolean scored, String... labels) {
            Set<String> wanted = new LinkedHashSet<>(java.util.Arrays.asList(labels));
            return outcomes.stream()
                    .filter(o -> o.testCase.isScored() == scored)
                    .filter(o -> wanted.contains(o.label))
                    .count();
        }

        void print(String title, boolean retrievalOnly) {
            List<BenchmarkOutcome> scored = outcomes.stream()
                    .filter(o -> o.testCase.isScored()).collect(Collectors.toList());
            int n = scored.size();
            System.out.println("== " + title + " (" + outcomes.size() + " casi, " + n + " valutati)");
            if (n > 0) {
                line("ricerca: primo posto", scored.stream().filter(o -> o.rank == 1).count(), n);
                line("ricerca: primi 3", scored.stream().filter(o -> o.rank >= 1 && o.rank <= 3).count(), n);
                line("ricerca: nel top-K", scored.stream().filter(o -> o.rank >= 1).count(), n);
            }
            if (retrievalOnly) return;
            if (n > 0) {
                long rightFirst = count(true, "right_first");
                long wrongSelect = count(true, "wrong_select");
                long rightClarify = count(true, "right_after_clarify");
                line("giusto al primo turno", rightFirst, n);
                line("giusto entro il chiarimento", rightFirst + rightClarify, n);
                line("selezione sbagliata senza avviso", wrongSelect + count(true, "wrong_none"), n);
                line("vicolo cieco o scelta errata", count(true, "dead_end", "wrong_after_clarify"), n);
                line("precisione delle selezioni", rightFirst, rightFirst + wrongSelect);
            }
            long offTopic = outcomes.stream().filter(o -> o.testCase.isOffTopic()).count();
            if (offTopic > 0) line("fuori tema respinti", count(false, "offtopic_ok"), offTopic);
            long clarified = outcomes.stream().filter(o -> RoutingDecision.CLARIFY.equals(o.action)).count();
            line("domande di chiarimento", clarified, outcomes.size());
        }

        private void line(String label, long hits, long total) {
            double[] ci = wilson(hits, total);
            System.out.printf("  %-34s %3d/%-3d %5.1f%%  (IC 95%% %.0f-%.0f)%n", label, hits, total,
                    total == 0 ? 0.0 : 100.0 * hits / total, ci[0], ci[1]);
        }

        static double[] wilson(long hits, long total) {
            if (total == 0) return new double[] {0.0, 0.0};
            double z = 1.96;
            double p = (double) hits / total;
            double denominator = 1 + z * z / total;
            double centre = (p + z * z / (2 * total)) / denominator;
            double margin = z * Math.sqrt(p * (1 - p) / total + z * z / (4.0 * total * total)) / denominator;
            return new double[] {100 * Math.max(0, centre - margin), 100 * Math.min(1, centre + margin)};
        }
    }
}
