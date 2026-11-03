package it.unical.uniticket;

import it.unical.uniticket.catalog.Catalog;
import it.unical.uniticket.catalog.Category;
import it.unical.uniticket.estimate.Estimate;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

/** Dati comuni ai test: il catalogo vero e qualche scorciatoia. */
public final class TestData {

    public static final Catalog CATALOG = Catalog.load(Path.of("data/catalog.json"));

    private TestData() {
    }

    public static Category form(String id) {
        return CATALOG.byId(id).orElseThrow(() -> new IllegalArgumentException("Modulo inesistente: " + id));
    }

    /** Una stima: coppie (id, quota) seguite dalle quote di "nessun modulo" e "servono informazioni". */
    public static Estimate estimate(String structure, double noMatch, double needsInfo, Object... formShares) {
        List<Estimate.Share> forms = new ArrayList<>();
        for (int i = 0; i < formShares.length; i += 2) {
            forms.add(new Estimate.Share(form((String) formShares[i]), (Double) formShares[i + 1]));
        }
        return new Estimate(forms, noMatch, needsInfo, structure);
    }
}
