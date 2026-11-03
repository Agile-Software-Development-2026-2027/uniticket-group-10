package it.unical.uniticket.dialog;

import it.unical.uniticket.catalog.Category;
import java.util.List;

/**
 * La risposta del bot a un messaggio.
 *
 * @param kind    l'esito del turno
 * @param text    il testo per l'utente
 * @param options i moduli proposti: uno se è sicuro, più d'uno se c'è incertezza
 * @param trace   come si è arrivati alla risposta (ricerca, modello, regola); stampata con --debug
 */
public record Reply(Kind kind, String text, List<Category> options, List<String> trace) {

    public enum Kind {
        /** Modulo individuato con sicurezza. */
        SELECTED,
        /** L'utente ha scelto tra le opzioni o confermato la proposta. */
        CONFIRMED,
        /** Un solo modulo, di un dipartimento non indicato: va confermato. */
        CONFIRM_STRUCTURE,
        /** Serve una precisazione. */
        CLARIFY,
        /** Domande esaurite: restano le opzioni migliori. */
        SHORTLIST,
        /** Nessun modulo adatto. */
        NO_MATCH,
        /** Il modello non risponde: opzioni della sola ricerca. */
        DEGRADED
    }

    /** La conversazione su questa richiesta è arrivata a una conclusione. */
    public boolean isFinal() {
        return kind == Kind.SELECTED || kind == Kind.CONFIRMED || kind == Kind.NO_MATCH;
    }
}
