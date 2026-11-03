package it.unical.uniticket.estimate;

import it.unical.uniticket.catalog.Category;
import java.util.List;

/**
 * La stima del modello: quanto è probabile ogni ipotesi. Le quote sommano a 1 su tre tipi di
 * ipotesi: i singoli moduli, "nessun modulo va bene", "l'utente ha detto troppo poco".
 *
 * <p>È l'unica cosa che il modello restituisce: da qui in poi decide il codice.
 *
 * @param forms     moduli con quota maggiore di zero, dal più probabile
 * @param structure slug della struttura che il modello ricava dalla conversazione, o null
 */
public record Estimate(List<Share> forms, double noMatch, double needsInfo, String structure) {

    public record Share(Category category, double share) {
    }

    public Estimate withStructure(String verified) {
        return new Estimate(forms, noMatch, needsInfo, verified);
    }
}
