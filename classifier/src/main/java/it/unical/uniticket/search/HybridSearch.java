package it.unical.uniticket.search;

import it.unical.uniticket.Http;
import it.unical.uniticket.catalog.Category;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Fonde BM25 e ricerca semantica con Reciprocal Rank Fusion: ogni modulo prende
 * {@code 1 / (60 + posizione)} da ciascuna classifica. Conta solo la posizione, quindi punteggi
 * BM25 e coseni, che hanno scale diverse, non vanno normalizzati.
 */
public final class HybridSearch implements Search {

    private static final int RRF_K = 60;
    private static final int DEPTH = 100;

    private final Search lexical;
    private final Search semantic;

    public HybridSearch(Search lexical, Search semantic) {
        this.lexical = lexical;
        this.semantic = semantic;
    }

    @Override
    public List<Hit> search(String query, int limit) {
        Map<String, Category> categories = new LinkedHashMap<>();
        Map<String, Double> scores = new LinkedHashMap<>();
        List<List<Hit>> rankings = new ArrayList<>();
        rankings.add(lexical.search(query, Math.max(DEPTH, limit)));
        try {
            rankings.add(semantic.search(query, Math.max(DEPTH, limit)));
        } catch (Http.ServiceException e) {
            // Ollama può cadere a metà conversazione: resta la ricerca lessicale.
            System.err.println("Ricerca semantica non disponibile: " + e.getMessage());
        }
        for (List<Hit> ranking : rankings) {
            for (int rank = 0; rank < ranking.size(); rank++) {
                Category category = ranking.get(rank).category();
                categories.put(category.id(), category);
                scores.merge(category.id(), 1.0 / (RRF_K + rank + 1), Double::sum);
            }
        }
        return scores.entrySet().stream()
                .map(e -> new Hit(categories.get(e.getKey()), e.getValue()))
                .sorted(Comparator.comparingDouble(Hit::score).reversed())
                .limit(limit)
                .toList();
    }

    @Override
    public String name() {
        return lexical.name() + " + " + semantic.name() + " (RRF)";
    }
}
