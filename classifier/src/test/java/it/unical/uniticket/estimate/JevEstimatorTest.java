package it.unical.uniticket.estimate;

import static it.unical.uniticket.TestData.CATALOG;
import static it.unical.uniticket.TestData.form;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import it.unical.uniticket.Json;
import it.unical.uniticket.catalog.Category;
import java.util.List;
import org.junit.jupiter.api.Test;

/** La lettura delle risposte di Jev, senza chiamare il modello. */
class JevEstimatorTest {

    private static final List<Category> CANDIDATES = List.of(
            form("dibest/richiesta-certificato-di-laurea"),
            form("dimes/richiesta-certificato-di-iscrizionelaureadiploma-supplement"));

    private final JevEstimator jev = new JevEstimator(CATALOG, "chiave", "jev-1.14.0");

    @Test
    void jevRicomponeLeProbabilitaNellaStessaStima() {
        // vago 0,3 → 0; adatto 0,7 → 1: tutta la quota va ai moduli, divisa come dice la Choice.
        Estimate estimate = jev.parse(Json.parse("""
                {"vago": {"noul": 0.3}, "struttura": {"choice": "non_indicata"},
                 "modulo": {"probabilities": {"M1": 0.5, "M2": 0.5}},
                 "adatto_M1": {"noul": 0.7}, "adatto_M2": {"noul": 0.5}}"""), CANDIDATES);
        assertEquals(0.5, estimate.forms().get(0).share(), 1e-9);
        assertEquals(0.0, estimate.noMatch(), 1e-9);
        assertEquals(0.0, estimate.needsInfo(), 1e-9);
        assertNull(estimate.structure());
    }

    @Test
    void jevConModuliNonAdattiDiceNessunModulo() {
        Estimate estimate = jev.parse(Json.parse("""
                {"vago": {"noul": 0.1}, "struttura": {"choice": "DiBEST"},
                 "modulo": {"probabilities": {"M1": 0.9, "M2": 0.1}},
                 "adatto_M1": {"noul": 0.2}, "adatto_M2": {"noul": 0.1}}"""), CANDIDATES);
        assertEquals(1.0, estimate.noMatch(), 1e-9);
        assertEquals("dibest", estimate.structure());
    }

    @Test
    void laNotaDiJevSiLeggeTraZeroVirgolaTreEZeroVirgolaSette() {
        assertEquals(0.0, JevEstimator.yes(0.2), 1e-9);
        assertEquals(0.5, JevEstimator.yes(0.5), 1e-9);
        assertEquals(1.0, JevEstimator.yes(0.9), 1e-9);
    }
}
