package it.unical.uniticket.search;

import it.unical.uniticket.catalog.Category;
import java.util.List;

/** Trova i moduli più vicini a un testo, dal più rilevante. */
public interface Search {

    record Hit(Category category, double score) {
    }

    List<Hit> search(String query, int limit);

    /** Il nome che compare nella traccia del turno. */
    String name();
}
