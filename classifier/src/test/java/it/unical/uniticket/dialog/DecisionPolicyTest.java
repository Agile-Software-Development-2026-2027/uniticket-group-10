package it.unical.uniticket.dialog;

import static it.unical.uniticket.TestData.CATALOG;
import static it.unical.uniticket.TestData.estimate;
import static it.unical.uniticket.TestData.form;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertTrue;

import it.unical.uniticket.dialog.DecisionPolicy.Clarify;
import it.unical.uniticket.dialog.DecisionPolicy.ConfirmStructure;
import it.unical.uniticket.dialog.DecisionPolicy.Decision;
import it.unical.uniticket.dialog.DecisionPolicy.NoMatch;
import it.unical.uniticket.dialog.DecisionPolicy.Selected;
import it.unical.uniticket.dialog.DecisionPolicy.Shortlist;
import it.unical.uniticket.estimate.Estimate;
import java.util.List;
import org.junit.jupiter.api.Test;

/** La regola di decisione, su stime preparate a mano: nessun modello. */
class DecisionPolicyTest {

    private static final String ESSE3 = "ict/e3-richiesta-assistenza-esse3";
    private static final String UNICONTR = "aru/unicontr-assistenza-problemi-tecnici";
    private static final String DIBEST = "dibest/richiesta-certificato-di-laurea";
    private static final String DIMES = "dimes/richiesta-certificato-di-iscrizionelaureadiploma-supplement";

    private final DecisionPolicy policy = new DecisionPolicy(DecisionPolicy.Params.DEFAULT);

    // ---------------------------------------------------------------- la regola dell'80%

    @Test
    void unModuloCentraleSicuroVieneSelezionato() {
        assertInstanceOf(Selected.class, policy.decide(estimate(null, 0.05, 0, ESSE3, 0.95), 0));
    }

    @Test
    void contaLaQuotaCumulataNonLaSingolaIpotesi() {
        // 34% al primo e il resto sparso: nessuna ipotesi da sola arriva all'80%, quindi si chiede.
        var estimate = estimate(null, 0.22, 0.22, ESSE3, 0.34, DIBEST, 0.11, DIMES, 0.11);
        assertInstanceOf(Clarify.class, policy.decide(estimate, 0));
    }

    @Test
    void lOrdineDelleIpotesiNonDipendeDaComeArrivano() {
        Decision decision = policy.decide(estimate(null, 0.05, 0, DIBEST, 0.05, ESSE3, 0.9), 0);
        assertEquals(form(ESSE3), assertInstanceOf(Selected.class, decision).category());
    }

    @Test
    void ilDubbioTraUnModuloENessunoSiRisolveChiedendo() {
        Clarify clarify = assertInstanceOf(Clarify.class, policy.decide(estimate(null, 0.5, 0, ESSE3, 0.5), 0));
        assertEquals(List.of(form(ESSE3)), clarify.options());
    }

    @Test
    void leOpzioniMostrateSonoAlPiuCinque() {
        List<Estimate.Share> twelve = CATALOG.categories().subList(0, 12).stream()
                .map(c -> new Estimate.Share(c, 1.0 / 12)).toList();
        Clarify clarify = assertInstanceOf(Clarify.class, policy.decide(new Estimate(twelve, 0, 0, null), 0));
        assertEquals(5, clarify.options().size());
    }

    // ---------------------------------------------------------------- nessun modulo e richieste vaghe

    @Test
    void soloNessunModuloVuolDireNessunModulo() {
        assertInstanceOf(NoMatch.class, policy.decide(estimate(null, 0.9, 0.1, ESSE3, 0.0), 0));
    }

    @Test
    void unMessaggioVagoProduceUnaDomandaSenzaOpzioni() {
        Clarify clarify = assertInstanceOf(Clarify.class, policy.decide(estimate(null, 0, 1), 0));
        assertTrue(clarify.options().isEmpty());
        assertEquals("Puoi darmi qualche dettaglio in più?", clarify.question());
    }

    @Test
    void unaStimaVuotaNonVieneLettaComeCertezza() {
        assertInstanceOf(Clarify.class, policy.decide(estimate(null, 0, 0), 0));
    }

    // ---------------------------------------------------------------- le domande

    @Test
    void stessaPraticaInDueDipartimentiFaChiedereIlDipartimento() {
        var decision = assertInstanceOf(Clarify.class, policy.decide(estimate(null, 0, 0, DIBEST, 0.5, DIMES, 0.5), 0));
        assertEquals(List.of(form(DIBEST), form(DIMES)), decision.options());
        assertEquals("A quale corso di studi o dipartimento fai riferimento?", decision.question());
    }

    @Test
    void conModuliDegliUfficiCentraliChiedeQualeScegliere() {
        Clarify clarify = assertInstanceOf(Clarify.class,
                policy.decide(estimate(null, 0, 0, ESSE3, 0.5, UNICONTR, 0.5), 0));
        assertEquals("Quale di questi corrisponde alla tua richiesta?", clarify.question());
    }

    @Test
    void finiteLeDomandeSiMostranoLeOpzioni() {
        Decision decision = policy.decide(estimate(null, 0, 0, DIBEST, 0.5, DIMES, 0.5), 3);
        assertEquals(List.of(form(DIBEST), form(DIMES)), assertInstanceOf(Shortlist.class, decision).options());
    }

    @Test
    void finiteLeDomandeSenzaOpzioniNonSiInsiste() {
        assertInstanceOf(NoMatch.class, policy.decide(estimate(null, 0, 1), 3));
    }

    // ---------------------------------------------------------------- i moduli di dipartimento

    @Test
    void unModuloDiDipartimentoSenzaStrutturaVaConfermato() {
        assertInstanceOf(ConfirmStructure.class, policy.decide(estimate(null, 0, 0, DIBEST, 1.0), 0));
    }

    @Test
    void unModuloDiDipartimentoConLaStrutturaVerificataVieneSelezionato() {
        assertInstanceOf(Selected.class, policy.decide(estimate("dibest", 0, 0, DIBEST, 1.0), 0));
    }

    @Test
    void unModuloDiUnAltroDipartimentoNonECerto() {
        assertInstanceOf(ConfirmStructure.class, policy.decide(estimate("fisica", 0, 0, DIBEST, 1.0), 0));
    }

    @Test
    void finiteLeDomandeUnModuloDiDipartimentoDiventaUnaProposta() {
        Decision decision = policy.decide(estimate(null, 0, 0, DIBEST, 1.0), 3);
        assertEquals(List.of(form(DIBEST)), assertInstanceOf(Shortlist.class, decision).options());
    }

    // ---------------------------------------------------------------- la traccia

    @Test
    void laSpiegazioneRiportaLeIpotesiELaDecisione() {
        Estimate estimate = estimate(null, 0.1, 0, ESSE3, 0.5, UNICONTR, 0.4);
        String explanation = policy.explain(estimate, policy.decide(estimate, 0));
        assertTrue(explanation.startsWith("Ipotesi fino al 80%: "), explanation);
        assertTrue(explanation.contains(form(ESSE3).name() + " 50%, " + form(UNICONTR).name() + " 40%"), explanation);
        assertTrue(explanation.endsWith("→ Clarify"), explanation);
    }
}
