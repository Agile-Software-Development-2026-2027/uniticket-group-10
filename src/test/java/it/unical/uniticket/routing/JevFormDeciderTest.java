package it.unical.uniticket.routing;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import it.unical.uniticket.access.UserProfile;
import it.unical.uniticket.api.dto.CategoryFormSchema;
import it.unical.uniticket.llm.JevClient;
import it.unical.uniticket.rag.UniTicketRagEngine.ScoredCategory;
import junit.framework.TestCase;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class JevFormDeciderTest extends TestCase {
    private static final double DELTA = 1e-9;

    private final ObjectMapper mapper = new ObjectMapper();

    /** Sostituisce il servizio: ricorda le domande ricevute e restituisce risposte fisse. */
    private static final class ScriptedJev extends JevClient {
        private final JsonNode answers;
        private final RuntimeException failure;
        JsonNode state;
        JsonNode questions;

        ScriptedJev(JsonNode answers, RuntimeException failure) {
            super("chiave", "jev-prova");
            this.answers = answers;
            this.failure = failure;
        }

        @Override
        public JsonNode ask(JsonNode state, JsonNode questions) {
            this.state = state;
            this.questions = questions;
            if (failure != null) throw failure;
            return answers;
        }
    }

    private static ScoredCategory candidate(String title) {
        return scored(0.8, title);
    }

    private static ScoredCategory scored(double similarity, String title) {
        CategoryFormSchema form = new CategoryFormSchema();
        form.structureSlug = "ict";
        form.structureName = "ICT";
        form.categoryTitle = title;
        form.compositeSlug = "ict__" + title.toLowerCase();
        form.accessible = true;
        return new ScoredCategory(form, 1.0, 0.0, similarity, Collections.singletonList(form));
    }

    private static List<ScoredCategory> candidates(int count) {
        List<ScoredCategory> result = new ArrayList<>();
        for (int i = 1; i <= count; i++) result.add(candidate("Modulo" + i));
        return result;
    }

    /** Risposte di Jev. Il campo confidence è volutamente diverso da ogni valore atteso. */
    private ObjectNode answers(String chosen, double[] probabilities, double[] fits) {
        ObjectNode answers = mapper.createObjectNode();
        ObjectNode choice = answers.putObject(JevFormDecider.CHOICE_QUESTION);
        choice.put("type", "choice").put("choice", chosen).put("confidence", 0.123);
        ObjectNode map = choice.putObject("probabilities");
        for (int i = 0; i < probabilities.length; i++) {
            map.put(String.valueOf(i + 1), probabilities[i]);
            answers.putObject(JevFormDecider.FIT_QUESTION_PREFIX + (i + 1))
                    .put("type", "noul").put("noul", fits[i]);
        }
        return answers;
    }

    private static double[] values(double... values) {
        return values;
    }

    private DeciderVerdict decide(JsonNode answers, int candidateCount) {
        return new JevFormDecider(new ScriptedJev(answers, null))
                .decide("richiesta", candidates(candidateCount), UserProfile.unknown());
    }

    private RoutingDecision route(JsonNode answers, List<ScoredCategory> candidates) {
        DeciderVerdict verdict = new JevFormDecider(new ScriptedJev(answers, null))
                .decide("richiesta", candidates, UserProfile.unknown());
        return new RoutingPolicy().apply("richiesta", candidates, verdict, UserProfile.unknown());
    }

    public void testEveryCandidateIsAnOptionAndHasItsOwnFitQuestion() {
        ScriptedJev jev = new ScriptedJev(answers("1", values(1.0, 0.0), values(0.9, 0.1)), null);
        new JevFormDecider(jev).decide("richiesta",
                Arrays.asList(candidate("Wifi"), candidate("Mensa")), UserProfile.unknown());

        assertEquals(3, jev.questions.size());
        JsonNode choice = jev.questions.path(JevFormDecider.CHOICE_QUESTION);
        assertEquals("choice", choice.path("type").asText());
        assertEquals(2, choice.path("criteria").size());
        assertTrue(choice.path("criteria").path("1").asText().startsWith("Wifi"));
        assertTrue(choice.path("criteria").path("2").asText().startsWith("Mensa"));

        JsonNode fit = jev.questions.path(JevFormDecider.FIT_QUESTION_PREFIX + "2");
        assertEquals("noul", fit.path("type").asText());
        assertTrue(fit.path("instructions").path("form").asText().startsWith("Mensa"));
        assertTrue(fit.path("criteria").has("true"));
        assertTrue(fit.path("criteria").has("false"));
    }

    public void testStateCarriesTheRequestAndTheProfile() {
        ScriptedJev jev = new ScriptedJev(answers("1", values(1.0), values(0.9)), null);
        new JevFormDecider(jev).decide("il wifi non va", candidates(1),
                UserProfile.of(UserProfile.Role.STUDENT, "demacs"));
        assertEquals("il wifi non va", jev.state.path("request").asText());
        assertEquals("studente, struttura demacs", jev.state.path("user_profile").asText());
    }

    public void testUnknownProfileIsLeftOut() {
        ScriptedJev jev = new ScriptedJev(answers("1", values(1.0), values(0.9)), null);
        new JevFormDecider(jev).decide("richiesta", candidates(1), UserProfile.unknown());
        assertFalse(jev.state.has("user_profile"));
    }

    /** Jev giudica solo la pertinenza: lo stato dei moduli spetta a RoutingPolicy. */
    public void testFormStatusNeverReachesJev() {
        ScoredCategory closed = candidate("Trasferimento");
        closed.schema.accessible = false;
        closed.schema.accessRestrictionReason = "HTTP 404: Moduli disponibili dal I luglio";
        closed.schema.jevCriterionSummary = "Richiesta: Trasferimento | Disponibilità osservata: closed";
        ScriptedJev jev = new ScriptedJev(answers("1", values(1.0), values(0.9)), null);
        new JevFormDecider(jev).decide("richiesta", Collections.singletonList(closed), UserProfile.unknown());
        String sent = jev.questions.toString() + jev.state;
        assertFalse(sent, sent.contains("Disponibilità"));
        assertFalse(sent, sent.contains("luglio"));
    }

    public void testConfidenceIsThePickProbabilityNotTheConfidenceField() {
        DeciderVerdict verdict = decide(answers("2", values(0.1, 0.9), values(0.2, 0.95)), 2);
        assertEquals(1, verdict.bestIndex);
        assertEquals(0.9, verdict.confidence, DELTA);
        assertFalse(verdict.failed);
    }

    public void testConfidenceCannotExceedTheFitOfThePick() {
        DeciderVerdict verdict = decide(answers("1", values(0.95, 0.05), values(0.6, 0.1)), 2);
        assertEquals(0.6, verdict.confidence, DELTA);
    }

    public void testNoFittingCandidateIsNoMatchEvenWithASureChoice() {
        DeciderVerdict verdict = decide(answers("1", values(0.99, 0.01), values(0.1, 0.05)), 2);
        assertEquals(DeciderVerdict.NO_MATCH, verdict.bestIndex);
        assertFalse(verdict.failed);
    }

    public void testFitAtTheThresholdIsNotNoMatch() {
        DeciderVerdict verdict = decide(answers("1", values(1.0), values(JevFormDecider.MIN_FIT)), 1);
        assertEquals(0, verdict.bestIndex);
    }

    public void testAnotherFittingCandidateAvoidsNoMatchButNotTheDoubt() {
        DeciderVerdict verdict = decide(answers("1", values(0.9, 0.1), values(0.1, 0.8)), 2);
        assertEquals(0, verdict.bestIndex);
        assertEquals(0.1, verdict.confidence, DELTA);
    }

    public void testCloseCandidatesBecomeAlternativesMostLikelyFirst() {
        DeciderVerdict verdict = decide(
                answers("1", values(0.4, 0.2, 0.35, 0.05), values(0.9, 0.9, 0.9, 0.9)), 4);
        assertEquals(Arrays.asList(2, 1), verdict.alternatives);
    }

    public void testClearLeaderHasNoAlternatives() {
        DeciderVerdict verdict = decide(answers("1", values(0.8, 0.2), values(0.9, 0.9)), 2);
        assertTrue(verdict.alternatives.isEmpty());
    }

    /** Se questo test cade, le alternative hanno iniziato a bloccare selezioni altrimenti valide. */
    public void testAlternativesNeverBlockAPickAboveTheConfidenceThreshold() {
        double pick = RoutingPolicy.SELECT_MIN_CONFIDENCE;
        DeciderVerdict verdict = decide(answers("1", values(pick, 1.0 - pick), values(0.9, 0.9)), 2);
        assertTrue(verdict.alternatives.isEmpty());
    }

    public void testReasoningShowsTheNumbers() {
        assertEquals("Jev: probabilità 0.90, pertinenza 0.80.",
                decide(answers("1", values(0.9, 0.1), values(0.8, 0.2)), 2).reasoning);
        assertEquals("Jev: pertinenza massima 0.20.",
                decide(answers("1", values(0.9, 0.1), values(0.1, 0.2)), 2).reasoning);
    }

    public void testServiceFailureIsReported() {
        DeciderVerdict verdict = new JevFormDecider(new ScriptedJev(null, new RuntimeException("HTTP 529")))
                .decide("richiesta", candidates(2), UserProfile.unknown());
        assertTrue(verdict.failed);
        assertTrue(verdict.reasoning, verdict.reasoning.contains("HTTP 529"));
    }

    public void testUnusableAnswersAreFailuresNotNoMatch() {
        ObjectNode unknownOption = answers("9", values(0.9, 0.1), values(0.9, 0.1));
        ObjectNode missingOption = answers("1", values(0.9, 0.1), values(0.9, 0.1));
        ((ObjectNode) missingOption.path(JevFormDecider.CHOICE_QUESTION).path("probabilities")).remove("2");
        ObjectNode missingFit = answers("1", values(0.9, 0.1), values(0.9, 0.1));
        missingFit.remove(JevFormDecider.FIT_QUESTION_PREFIX + "2");
        ObjectNode textualFit = answers("1", values(0.9, 0.1), values(0.9, 0.1));
        ((ObjectNode) textualFit.path(JevFormDecider.FIT_QUESTION_PREFIX + "1")).put("noul", "alta");

        for (JsonNode answers : Arrays.asList(unknownOption, missingOption, missingFit, textualFit,
                answers("1", values(1.5, 0.1), values(0.9, 0.1)),
                answers("1", values(0.9, 0.1), values(-0.1, 0.1)),
                mapper.missingNode(), mapper.createObjectNode())) {
            assertTrue(answers.toString(), decide(answers, 2).failed);
        }
    }

    public void testSurePickIsSelectedEvenWhenSearchIsWeak() {
        List<ScoredCategory> weak = Arrays.asList(scored(0.1, "A"), scored(0.1, "B"));
        RoutingDecision decision = route(answers("2", values(0.05, 0.95), values(0.1, 0.9)), weak);
        assertEquals(RoutingDecision.SELECT, decision.action);
        assertEquals("ict__b", decision.selectedCompositeSlug);
        assertEquals(0.9, decision.confidence, DELTA);
    }

    /** Una scelta con una sola opzione vale sempre 1: è la pertinenza a decidere. */
    public void testLoneCandidateIsNotSelectedOnTheChoiceAlone() {
        RoutingDecision decision = route(answers("1", values(1.0), values(0.5)), candidates(1));
        assertEquals(RoutingDecision.CLARIFY, decision.action);
    }

    public void testOffTopicRequestIsRefusedWhenSearchIsWeak() {
        List<ScoredCategory> weak = Arrays.asList(scored(0.4, "A"), scored(0.3, "B"));
        RoutingDecision decision = route(answers("1", values(0.9, 0.1), values(0.05, 0.02)), weak);
        assertEquals(RoutingDecision.NONE, decision.action);
    }

    public void testTiedCandidatesAreBothOffered() {
        RoutingDecision decision = route(answers("2", values(0.45, 0.5, 0.05), values(0.9, 0.9, 0.2)),
                candidates(3));
        assertEquals(RoutingDecision.CLARIFY, decision.action);
        assertEquals(2, decision.clarifyOptions.size());
        assertEquals("ict__modulo2", decision.clarifyOptions.get(0).schema.compositeSlug);
        assertEquals("ict__modulo1", decision.clarifyOptions.get(1).schema.compositeSlug);
        assertFalse(decision.clarifyingQuestion.trim().isEmpty());
    }

    public void testServiceDownFallsBackToTheSearchResults() {
        List<ScoredCategory> candidates = candidates(4);
        DeciderVerdict verdict = new JevFormDecider(new ScriptedJev(null, new RuntimeException("giù")))
                .decide("richiesta", candidates, UserProfile.unknown());
        RoutingDecision decision = new RoutingPolicy().apply("richiesta", candidates, verdict, UserProfile.unknown());
        assertEquals(RoutingDecision.CLARIFY, decision.action);
        assertEquals(3, decision.clarifyOptions.size());
    }
}
