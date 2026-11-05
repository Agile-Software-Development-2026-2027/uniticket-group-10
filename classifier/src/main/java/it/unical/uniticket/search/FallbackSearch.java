package it.unical.uniticket.search;

import it.unical.uniticket.Http;
import java.util.List;

/**
 * Una ricerca con una riserva: se la principale non risponde (Ollama caduto a metà conversazione),
 * si usa l'altra per quella domanda e si riprova la principale alla successiva.
 */
public final class FallbackSearch implements Search {

    private final Search primary;
    private final Search fallback;

    public FallbackSearch(Search primary, Search fallback) {
        this.primary = primary;
        this.fallback = fallback;
    }

    @Override
    public List<Hit> search(String query, int limit) {
        try {
            return primary.search(query, limit);
        } catch (Http.ServiceException e) {
            System.err.println(primary.name() + " non disponibile (" + e.getMessage() + "): uso " + fallback.name() + ".");
            return fallback.search(query, limit);
        }
    }

    @Override
    public String name() {
        return primary.name() + " (riserva " + fallback.name() + ")";
    }
}
