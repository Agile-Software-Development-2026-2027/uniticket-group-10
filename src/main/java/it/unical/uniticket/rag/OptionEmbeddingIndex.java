package it.unical.uniticket.rag;

import it.unical.uniticket.api.dto.CategoryFormSchema;
import it.unical.uniticket.api.dto.FieldSchema;
import it.unical.uniticket.api.dto.OptionItem;
import it.unical.uniticket.llm.EmbeddingClient;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class OptionEmbeddingIndex {
    public static class OptionMatch {
        public final OptionItem option;
        public final double score;

        public OptionMatch(OptionItem option, double score) {
            this.option = option;
            this.score = score;
        }
    }

    private static class OptionEntry {
        final OptionItem option;
        final float[] vector;

        OptionEntry(OptionItem option, float[] vector) {
            this.option = option;
            this.vector = vector;
        }
    }

    private final EmbeddingClient embedder;
    private final Map<String, List<OptionEntry>> cache = new ConcurrentHashMap<>();

    public OptionEmbeddingIndex(EmbeddingClient embedder) {
        this.embedder = embedder;
    }

    public List<OptionMatch> findTopCandidates(String rawValue, CategoryFormSchema schema,
                                                FieldSchema field, int k) {
        if (rawValue == null || rawValue.trim().isEmpty() || schema == null || field == null
                || field.options == null || field.options.isEmpty() || k <= 0) {
            return Collections.emptyList();
        }
        List<OptionEntry> entries = cache.computeIfAbsent(schema.compositeSlug + "::" + field.name,
                ignored -> embedOptions(field));
        if (entries.isEmpty()) return Collections.emptyList();

        float[] queryVector = embedder.embed(rawValue);
        List<OptionMatch> scored = new ArrayList<>(entries.size());
        for (OptionEntry entry : entries) {
            scored.add(new OptionMatch(entry.option, EmbeddingUtils.cosine(queryVector, entry.vector)));
        }
        scored.sort(Comparator.comparingDouble((OptionMatch match) -> match.score).reversed());
        return new ArrayList<>(scored.subList(0, Math.min(k, scored.size())));
    }

    private List<OptionEntry> embedOptions(FieldSchema field) {
        List<OptionItem> options = field.options;
        if (options == null || options.isEmpty()) return Collections.emptyList();
        List<String> texts = new ArrayList<>(options.size());
        for (OptionItem option : options) {
            String label = option.label != null && !option.label.trim().isEmpty()
                    ? option.label : option.value;
            texts.add(option.value != null && !option.value.equals(label)
                    ? label + " (" + option.value + ")" : label);
        }
        List<float[]> vectors = embedder.embedBatch(texts);
        if (vectors.size() != options.size()) {
            throw new IllegalStateException("Numero di embeddings diverso dal numero di opzioni.");
        }
        List<OptionEntry> result = new ArrayList<>(options.size());
        for (int i = 0; i < options.size(); i++) result.add(new OptionEntry(options.get(i), vectors.get(i)));
        return result;
    }
}
