package it.unical.uniticket.routing;

import it.unical.uniticket.rag.UniTicketRagEngine.ScoredCategory;

import java.util.List;

/**
 * Riceve i passi della classificazione mentre avvengono, nell'ordine in cui avvengono.
 * I passi si ripetono se la ricerca viene estesa ai moduli chiusi.
 */
public interface RoutingTrace {
    RoutingTrace SILENT = new RoutingTrace() {
    };

    /** Risultati di una ricerca, nell'ordine e con la numerazione che vede il decisore. */
    default void searched(List<ScoredCategory> candidates, boolean closedFormsIncluded) {
    }

    /** Giudizio del decisore. Non arriva se la ricerca non ha trovato candidati. */
    default void judged(String deciderName, List<ScoredCategory> candidates, DeciderVerdict verdict) {
    }

    /** Esito definitivo del turno. */
    default void decided(RoutingDecision decision, String deciderName) {
    }
}
