package it.unical.uniticket.routing;

import it.unical.uniticket.access.UserProfile;
import it.unical.uniticket.api.dto.CategoryFormSchema;
import it.unical.uniticket.rag.UniTicketRagEngine.ScoredCategory;
import junit.framework.TestCase;

import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class RoutingPolicyTest extends TestCase {
    private final RoutingPolicy policy = new RoutingPolicy();

    private static CategoryFormSchema form(String structure, String title, String closedReason) {
        CategoryFormSchema form = new CategoryFormSchema();
        form.structureSlug = structure;
        form.structureName = structure.toUpperCase();
        form.categoryTitle = title;
        form.compositeSlug = structure + "__" + title.toLowerCase().replace(' ', '-');
        form.accessible = closedReason == null;
        form.accessRestrictionReason = closedReason;
        return form;
    }

    private static CategoryFormSchema open(String structure, String title) {
        return form(structure, title, null);
    }

    private static ScoredCategory practice(CategoryFormSchema... variants) {
        return scored(0.8, variants);
    }

    private static ScoredCategory scored(double similarity, CategoryFormSchema... variants) {
        return new ScoredCategory(variants[0], 1.0, 0.0, similarity, Arrays.asList(variants));
    }

    private static DeciderVerdict pick(int index, Integer... alternatives) {
        return DeciderVerdict.match(index, Arrays.asList(alternatives), null, "motivo", "");
    }

    private static UserProfile student(String department) {
        return UserProfile.of(UserProfile.Role.STUDENT, department);
    }

    public void testSingleFormIsSelected() {
        List<ScoredCategory> candidates = Collections.singletonList(practice(open("ict", "Wifi")));
        RoutingDecision decision = policy.apply("il wifi", candidates, pick(0), student("dimes"));
        assertEquals(RoutingDecision.SELECT, decision.action);
        assertEquals("ict__wifi", decision.selectedCompositeSlug);
        assertFalse(decision.isClosedForm());
    }

    public void testNoMatchIsRespectedWhenSearchIsWeak() {
        List<ScoredCategory> candidates = Collections.singletonList(scored(0.5, open("ict", "Wifi")));
        RoutingDecision decision = policy.apply("che tempo fa", candidates,
                DeciderVerdict.noMatch("fuori tema"), student("dimes"));
        assertEquals(RoutingDecision.NONE, decision.action);
        assertTrue(decision.clarifyOptions.isEmpty());
    }

    public void testNoMatchIsReviewedWhenSearchIsStrong() {
        List<ScoredCategory> candidates = Collections.singletonList(scored(0.7, open("ict", "Wifi")));
        RoutingDecision decision = policy.apply("la SIM non funziona", candidates,
                DeciderVerdict.noMatch("incerto"), student("dimes"));
        assertEquals(RoutingDecision.CLARIFY, decision.action);
    }

    public void testWeakSimilarityAsksInsteadOfSelecting() {
        List<ScoredCategory> candidates = Arrays.asList(
                scored(0.4, open("ict", "A")), scored(0.3, open("ict", "B")));
        RoutingDecision decision = policy.apply("x", candidates, pick(0), student(null));
        assertEquals(RoutingDecision.CLARIFY, decision.action);
        assertEquals(2, decision.clarifyOptions.size());
    }

    public void testPickFarDownTheRankingAsksInsteadOfSelecting() {
        List<ScoredCategory> candidates = Arrays.asList(practice(open("ict", "A")),
                practice(open("ict", "B")), practice(open("ict", "C")), practice(open("ict", "D")));
        RoutingDecision decision = policy.apply("x", candidates, pick(3), student(null));
        assertEquals(RoutingDecision.CLARIFY, decision.action);
        assertEquals("ict__d", decision.clarifyOptions.get(0).schema.compositeSlug);
        assertEquals("ict__a", decision.clarifyOptions.get(1).schema.compositeSlug);
    }

    public void testCalibratedConfidenceReplacesTheSimilarityCheck() {
        List<ScoredCategory> candidates = Arrays.asList(
                scored(0.1, open("ict", "A")), scored(0.1, open("ict", "B")));
        DeciderVerdict sure = DeciderVerdict.match(1, Collections.emptyList(), 0.95, "", "");
        DeciderVerdict unsure = DeciderVerdict.match(1, Collections.emptyList(), 0.40, "", "");
        assertEquals(RoutingDecision.SELECT, policy.apply("x", candidates, sure, student(null)).action);
        assertEquals(RoutingDecision.CLARIFY, policy.apply("x", candidates, unsure, student(null)).action);
    }

    public void testFailedDeciderAsksInsteadOfGuessing() {
        List<ScoredCategory> candidates = Arrays.asList(
                practice(open("ict", "A")), practice(open("ict", "B")),
                practice(open("ict", "C")), practice(open("ict", "D")));
        RoutingDecision decision = policy.apply("x", candidates, DeciderVerdict.failed("errore"),
                student("dimes"));
        assertEquals(RoutingDecision.CLARIFY, decision.action);
        assertEquals(3, decision.clarifyOptions.size());
    }

    public void testNoCandidatesMeansNone() {
        RoutingDecision decision = policy.apply("x", Collections.emptyList(), pick(0), student(null));
        assertEquals(RoutingDecision.NONE, decision.action);
    }

    public void testClosedFormIsSelectedWithItsReason() {
        CategoryFormSchema closed = form("disu", "Trasferimento", "HTTP 404: Moduli disponibili dal I luglio al 31 agosto");
        RoutingDecision decision = policy.apply("voglio trasferirmi",
                Collections.singletonList(practice(closed)), pick(0), student("disu"));
        assertEquals(RoutingDecision.SELECT, decision.action);
        assertTrue(decision.isClosedForm());
        assertEquals("Moduli disponibili dal I luglio al 31 agosto", decision.closureReason);
    }

    public void testLoginDepartmentResolvesTheVariant() {
        ScoredCategory tesi = practice(open("dices", "Tesi"), open("disu", "Tesi"));
        RoutingDecision decision = policy.apply("voglio la tesi", Collections.singletonList(tesi),
                pick(0), student("disu"));
        assertEquals(RoutingDecision.SELECT, decision.action);
        assertEquals("disu__tesi", decision.selectedCompositeSlug);
        assertTrue(decision.departmentFromProfile);
        assertEquals(1, decision.otherDepartmentVariants.size());
    }

    public void testDepartmentNamedInTextBeatsTheLogin() {
        ScoredCategory tesi = practice(open("dices", "Tesi"), open("disu", "Tesi"));
        RoutingDecision decision = policy.apply("vorrei la tesi al DiCES",
                Collections.singletonList(tesi), pick(0), student("disu"));
        assertEquals("dices__tesi", decision.selectedCompositeSlug);
        assertFalse(decision.departmentFromProfile);
    }

    public void testFullDepartmentNameIsRecognised() {
        ScoredCategory tesi = practice(open("dices", "Tesi"), open("disu", "Tesi"));
        RoutingDecision decision = policy.apply("tesi a Studi Umanistici",
                Collections.singletonList(tesi), pick(0), student("dices"));
        assertEquals("disu__tesi", decision.selectedCompositeSlug);
    }

    public void testUnknownDepartmentAsksWhichOne() {
        ScoredCategory tesi = practice(open("dices", "Tesi"), open("disu", "Tesi"));
        RoutingDecision decision = policy.apply("voglio la tesi", Collections.singletonList(tesi),
                pick(0), student("dimeg"));
        assertEquals(RoutingDecision.CLARIFY, decision.action);
        assertEquals(2, decision.clarifyOptions.size());
    }

    public void testOwnClosedVariantIsNotSwappedForAnotherDepartment() {
        CategoryFormSchema ownClosed = form("desf", "Riconoscimento", "HTTP 404: Non attivo");
        ScoredCategory practice = practice(open("dimes", "Riconoscimento"), ownClosed);
        RoutingDecision decision = policy.apply("riconoscere esami", Collections.singletonList(practice),
                pick(0), student("desf"));
        assertEquals(RoutingDecision.SELECT, decision.action);
        assertEquals("desf__riconoscimento", decision.selectedCompositeSlug);
        assertTrue(decision.isClosedForm());
    }

    public void testSubstringOfADepartmentNameDoesNotCount() {
        ScoredCategory practice = practice(open("disu", "Tesi"), open("dices", "Tesi"));
        RoutingDecision decision = policy.apply("ho discusso con disumanita", Collections.singletonList(practice),
                pick(0), student(null));
        assertEquals(RoutingDecision.CLARIFY, decision.action);
    }

    private RoutingDecision reviewed(ScoredCategory pick, ScoredCategory top) {
        List<ScoredCategory> candidates = Collections.singletonList(pick);
        RoutingDecision decision = policy.apply("x", candidates, pick(0), student(null));
        return policy.reviewAgainstClosedForms(decision, Arrays.asList(top, pick), student(null));
    }

    public void testStrongerClosedFormIsOfferedNextToTheOpenPick() {
        ScoredCategory pick = scored(0.60, open("ict", "Aperto"));
        ScoredCategory closed = scored(0.65, form("ict", "Chiuso", "HTTP 404: Non attivo"));
        RoutingDecision decision = reviewed(pick, closed);
        assertEquals(RoutingDecision.CLARIFY, decision.action);
        assertEquals(2, decision.clarifyOptions.size());
    }

    public void testWeakerClosedFormDoesNotDisturbTheOpenPick() {
        ScoredCategory pick = scored(0.70, open("ict", "Aperto"));
        ScoredCategory closed = scored(0.65, form("ict", "Chiuso", "HTTP 404: Non attivo"));
        assertEquals(RoutingDecision.SELECT, reviewed(pick, closed).action);
    }

    public void testOpenTopResultDoesNotDisturbTheOpenPick() {
        ScoredCategory pick = scored(0.60, open("ict", "Aperto"));
        assertEquals(RoutingDecision.SELECT, reviewed(pick, scored(0.80, open("ict", "Altro"))).action);
    }

    public void testAlternativesProduceOptions() {
        List<ScoredCategory> candidates = Arrays.asList(scored(0.6, open("ict", "A")),
                scored(0.6, open("ict", "B")), scored(0.6, open("ict", "C")));
        RoutingDecision decision = policy.apply("x", candidates, pick(1, 2), student(null));
        assertEquals(RoutingDecision.CLARIFY, decision.action);
        assertEquals("ict__b", decision.clarifyOptions.get(0).schema.compositeSlug);
        assertEquals("ict__c", decision.clarifyOptions.get(1).schema.compositeSlug);
    }
}
