package it.unical.uniticket.catalog;

import static it.unical.uniticket.TestData.CATALOG;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class CatalogTest {

    @Test
    void contieneSoloIModuliDisponibili() {
        assertEquals(241, CATALOG.categories().size());
    }

    @Test
    void riconosceLaStrutturaDalCorsoDiStudi() {
        assertTrue(CATALOG.structuresNamedIn("sono laureato in ingegneria informatica").contains("dimes"));
        assertTrue(CATALOG.structuresNamedIn("Sono iscritta a Biologia").contains("dibest"));
    }

    @Test
    void nonRiconosceParoleIsolateOParti() {
        assertFalse(CATALOG.structuresNamedIn("sto fisicamente male").contains("fisica"));
        assertTrue(CATALOG.structuresNamedIn("vorrei un certificato").isEmpty());
    }

    @Test
    void scartaLeDescrizioniCheNonDiconoNulla() {
        assertEquals("", CatalogBuilder.summary("Dettaglia qui la tua richiesta.", "Richiesta generica"));
        assertEquals("Testo vero", CatalogBuilder.summary("**Testo** vero", "Titolo"));
    }
}
