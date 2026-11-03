package it.unical.uniticket.dialog;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.OptionalInt;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.ValueSource;

/** Le risposte chiuse: quelle che il bot capisce senza chiamare il modello. */
class UserChoiceTest {

    @ParameterizedTest
    @CsvSource({"2,1", "2.,1", "la 2,1", "opzione 3,2", "opzione 3.,2", "numero 1,0", "la prima,0", "seconda,1",
            "il terzo,2", "Il primo,0", "la seconda opzione,1"})
    void riconosceLeScelte(String text, int index) {
        assertEquals(OptionalInt.of(index), UserChoice.parse(text, 5));
    }

    @ParameterizedTest
    @ValueSource(strings = {"9", "4", "sono di fisica", "sono al 2 anno", "2 anni fa", "la prima volta che scrivo",
            "secondo me sì"})
    void nonForzaLeFrasiLibereInUnaScelta(String text) {
        assertTrue(UserChoice.parse(text, 3).isEmpty());
    }

    @ParameterizedTest
    @ValueSource(strings = {"no", "No.", "nessuna", "nessuna di queste", "non è questo", "altro"})
    void riconosceIRifiuti(String text) {
        assertTrue(UserChoice.isRejection(text));
    }

    @ParameterizedTest
    @ValueSource(strings = {"sì", "Sì!", "si", "Ok grazie", "va bene!", "perfetto.", "thanks"})
    void riconosceLeConferme(String text) {
        assertTrue(UserChoice.isAcceptance(text));
    }

    @ParameterizedTest
    @ValueSource(strings = {"sì ma devo anche fare altro", "sì, ma sono di fisica", "grazie ma non è questo",
            "ok, e per il rimborso?", "certo, è quello"})
    void unaFraseConAltroContenutoNonEUnaConferma(String text) {
        assertFalse(UserChoice.isAcceptance(text));
    }

    @ParameterizedTest
    @ValueSource(strings = {"no, volevo il rimborso", "non è la tessera che mi serve", "sono di altro dipartimento"})
    void unaCorrezioneConContenutoNonEUnRifiutoSecco(String text) {
        assertFalse(UserChoice.isRejection(text));
    }
}
