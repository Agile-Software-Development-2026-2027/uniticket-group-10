package it.unical.uniticket.estimate;

import it.unical.uniticket.catalog.Category;
import java.util.List;

/**
 * Chiede a un modello quale dei candidati serve all'utente. "Il modello stima, il codice decide":
 * chi implementa questa interfaccia non decide nulla, restituisce solo la stima.
 */
public interface Estimator {

    /**
     * @param conversation la conversazione finora
     * @param candidates   i moduli trovati dalla ricerca: il modello sceglie solo tra questi
     * @throws it.unical.uniticket.Http.ServiceException se il modello non risponde
     */
    Estimate estimate(List<Turn> conversation, List<Category> candidates);

    /** Il nome del modello, per la traccia e i risultati. */
    String name();
}
