package it.unical.uniticket.llm;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.jsoup.Connection;
import org.jsoup.Jsoup;
import org.jsoup.HttpStatusException;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class OllamaEmbeddingClient implements EmbeddingClient {
    private static final int MAX_BATCH_SIZE = 128;

    private final String ollamaBaseUrl;
    private final String modelName;
    private final ObjectMapper mapper = new ObjectMapper();

    public OllamaEmbeddingClient(String ollamaBaseUrl, String modelName) {
        String base = ollamaBaseUrl.endsWith("/")
                ? ollamaBaseUrl.substring(0, ollamaBaseUrl.length() - 1)
                : ollamaBaseUrl;
        if (base.endsWith("/api/chat") || base.endsWith("/api/embed")
                || base.endsWith("/api/embeddings")) {
            base = base.substring(0, base.lastIndexOf("/api/"));
        }
        this.ollamaBaseUrl = base;
        this.modelName = modelName;
    }

    @Override
    public float[] embed(String text) {
        List<float[]> batch = embedBatch(Collections.singletonList(text));
        return batch.isEmpty() ? new float[0] : batch.get(0);
    }

    @Override
    public List<float[]> embedBatch(List<String> texts) {
        if (texts == null || texts.isEmpty()) return Collections.emptyList();
        List<float[]> result = new ArrayList<>(texts.size());
        for (int start = 0; start < texts.size(); start += MAX_BATCH_SIZE) {
            int end = Math.min(start + MAX_BATCH_SIZE, texts.size());
            result.addAll(embedSingleBatch(texts.subList(start, end), start, end));
        }
        return result;
    }

    private List<float[]> embedSingleBatch(List<String> texts, int start, int end) {
        try {
            ObjectNode root = mapper.createObjectNode();
            root.put("model", modelName);
            ArrayNode input = root.putArray("input");
            for (String text : texts) input.add(text == null ? "" : text);

            Connection.Response response = Jsoup.connect(ollamaBaseUrl + "/api/embed")
                    .header("Content-Type", "application/json")
                    .requestBody(mapper.writeValueAsString(root))
                    .ignoreContentType(true)
                    .timeout(120_000)
                    .method(Connection.Method.POST)
                    .execute();

            JsonNode embeddings = mapper.readTree(response.body()).path("embeddings");
            if (!embeddings.isArray() || embeddings.size() != texts.size()) {
                throw new IllegalStateException("Risposta embeddings incompleta o non valida.");
            }
            List<float[]> result = new ArrayList<>(embeddings.size());
            for (JsonNode array : embeddings) {
                float[] vector = new float[array.size()];
                for (int i = 0; i < array.size(); i++) vector[i] = (float) array.get(i).asDouble();
                result.add(vector);
            }
            return result;
        } catch (HttpStatusException e) {
            throw new RuntimeException("Errore embeddings Ollama su " + ollamaBaseUrl
                    + " per il modello '" + modelName + "' nel batch " + start + "-" + (end - 1)
                    + ": HTTP " + e.getStatusCode() + " (" + e.getUrl() + ")", e);
        } catch (Exception e) {
            throw new RuntimeException("Errore embeddings Ollama su " + ollamaBaseUrl
                    + " per il modello '" + modelName + "' nel batch " + start + "-" + (end - 1)
                    + ": " + e.getMessage(), e);
        }
    }
}
