package it.unical.uniticket.search;

import com.fasterxml.jackson.databind.JsonNode;
import it.unical.uniticket.Http;
import it.unical.uniticket.Json;
import it.unical.uniticket.catalog.Catalog;
import it.unical.uniticket.catalog.Category;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Base64;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Ricerca per significato: embedding {@code bge-m3} calcolati in locale da Ollama e similarità del
 * coseno. Trova "ho perso il libretto" anche se il modulo dice "duplicato". Con 241 moduli un
 * confronto lineare è istantaneo.
 *
 * <p>I vettori dei moduli stanno in una cache su disco, indicizzata sull'hash del testo: cambiare un
 * form ricalcola solo quello.
 */
public final class SemanticSearch implements Search {

    private static final String MODEL = "bge-m3";

    private record Entry(Category category, float[] vector) {
    }

    private final String endpoint;
    private final List<Entry> entries = new ArrayList<>();

    public SemanticSearch(Catalog catalog, String ollamaUrl, Path cacheDir) {
        this.endpoint = ollamaUrl + "/api/embed";
        Path cacheFile = cacheDir.resolve(MODEL + ".json");
        Map<String, String> cache = new LinkedHashMap<>();
        if (Files.exists(cacheFile)) {
            Json.read(cacheFile).fields().forEachRemaining(e -> cache.put(e.getKey(), e.getValue().asText()));
        }
        List<String> missing = new ArrayList<>();
        for (Category category : catalog.categories()) {
            String text = catalog.embeddingText(category);
            if (!cache.containsKey(sha256(text))) {
                missing.add(text);
            }
        }
        if (!missing.isEmpty()) {
            List<float[]> vectors = embed(missing);
            for (int i = 0; i < missing.size(); i++) {
                cache.put(sha256(missing.get(i)), encode(vectors.get(i)));
            }
            Json.writePretty(cacheFile, cache);
        }
        for (Category category : catalog.categories()) {
            entries.add(new Entry(category, normalize(decode(cache.get(sha256(catalog.embeddingText(category)))))));
        }
    }

    @Override
    public List<Hit> search(String query, int limit) {
        float[] q = normalize(embed(List.of(query)).get(0));
        return entries.stream()
                .map(e -> new Hit(e.category(), dot(q, e.vector())))
                .sorted(Comparator.comparingDouble(Hit::score).reversed())
                .limit(limit)
                .toList();
    }

    @Override
    public String name() {
        return MODEL;
    }

    private List<float[]> embed(List<String> texts) {
        String body = Json.write(Map.of("model", MODEL, "input", texts));
        JsonNode rows = Json.parse(Http.post(endpoint, Map.of(), body, Duration.ofMinutes(2))).path("embeddings");
        if (rows.size() != texts.size()) {
            throw new Http.ServiceException("Ollama: attesi " + texts.size() + " vettori, ricevuti " + rows.size());
        }
        List<float[]> vectors = new ArrayList<>();
        for (JsonNode row : rows) {
            float[] v = new float[row.size()];
            for (int i = 0; i < v.length; i++) {
                v[i] = row.get(i).floatValue();
            }
            vectors.add(v);
        }
        return vectors;
    }

    private static double dot(float[] a, float[] b) {
        double sum = 0;
        for (int i = 0; i < a.length; i++) {
            sum += a[i] * b[i];
        }
        return sum;
    }

    private static float[] normalize(float[] v) {
        double norm = Math.sqrt(dot(v, v));
        float[] result = new float[v.length];
        for (int i = 0; i < v.length; i++) {
            result[i] = (float) (v[i] / norm);
        }
        return result;
    }

    private static String sha256(String text) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(text.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }

    private static String encode(float[] v) {
        ByteBuffer buffer = ByteBuffer.allocate(v.length * Float.BYTES).order(ByteOrder.LITTLE_ENDIAN);
        buffer.asFloatBuffer().put(v);
        return Base64.getEncoder().encodeToString(buffer.array());
    }

    private static float[] decode(String encoded) {
        ByteBuffer buffer = ByteBuffer.wrap(Base64.getDecoder().decode(encoded)).order(ByteOrder.LITTLE_ENDIAN);
        float[] v = new float[buffer.remaining() / Float.BYTES];
        buffer.asFloatBuffer().get(v);
        return v;
    }
}
