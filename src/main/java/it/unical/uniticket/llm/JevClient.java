package it.unical.uniticket.llm;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.jsoup.Connection;
import org.jsoup.Jsoup;

import java.io.IOException;

/**
 * Client per la System One API di TypeSafe, che serve il modello Jev.
 *
 * <p>Non è un {@link LlmClient}: Jev non genera testo, ma risponde a domande tipizzate su uno
 * stato. Le domande e il significato delle risposte stanno quindi in {@code JevFormDecider}.</p>
 *
 * <p>Le richieste escono dalla macchina e il servizio è ospitato negli Stati Uniti. La chiave
 * viaggia in un header, così non finisce mai negli URL o nei messaggi di errore.</p>
 */
public class JevClient {
    private static final String ENDPOINT = "https://api.typesafe.ai/v1/systemone";
    /** Timeout, tentativi e prima attesa sono i valori predefiniti dell'SDK ufficiale. */
    private static final int TIMEOUT_MILLIS = 10_000;
    private static final int MAX_ATTEMPTS = 3;
    private static final long FIRST_RETRY_MILLIS = 500;

    private final String apiKey;
    private final String modelName;
    private final String endpoint;
    private final long firstRetryMillis;
    private final ObjectMapper mapper = new ObjectMapper();

    public JevClient(String apiKey, String modelName) {
        this(apiKey, modelName, ENDPOINT, FIRST_RETRY_MILLIS);
    }

    JevClient(String apiKey, String modelName, String endpoint, long firstRetryMillis) {
        if (apiKey == null || apiKey.trim().isEmpty()) {
            throw new IllegalArgumentException("Per usare Jev serve la variabile TYPESAFE_API_KEY.");
        }
        this.apiKey = apiKey.trim();
        this.modelName = modelName;
        this.endpoint = endpoint;
        this.firstRetryMillis = firstRetryMillis;
    }

    public String modelName() {
        return modelName;
    }

    /** Pone le domande sullo stato e restituisce le risposte, con gli stessi nomi delle domande. */
    public JsonNode ask(JsonNode state, JsonNode questions) {
        try {
            String body = mapper.writeValueAsString(buildRequest(state, questions));
            long wait = firstRetryMillis;
            for (int attempt = 1; ; attempt++) {
                Connection.Response response = post(body);
                if (response.statusCode() == 200) return mapper.readTree(response.body()).path("answers");
                if (attempt == MAX_ATTEMPTS || !isTemporary(response.statusCode())) {
                    throw new IllegalStateException("HTTP " + response.statusCode() + ": "
                            + errorMessage(response.body()));
                }
                Thread.sleep(wait);
                wait *= 2;
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new RuntimeException("Chiamata Jev interrotta.", e);
        } catch (IOException | IllegalStateException e) {
            throw new RuntimeException("Errore chiamata Jev con il modello '" + modelName + "': "
                    + e.getMessage(), e);
        }
    }

    private Connection.Response post(String body) throws IOException {
        return Jsoup.connect(endpoint)
                .header("Content-Type", "application/json")
                .header("Authorization", "Bearer " + apiKey)
                .requestBody(body)
                .ignoreContentType(true)
                .ignoreHttpErrors(true)
                .timeout(TIMEOUT_MILLIS)
                .method(Connection.Method.POST)
                .execute();
    }

    ObjectNode buildRequest(JsonNode state, JsonNode questions) {
        ObjectNode root = mapper.createObjectNode();
        root.put("model", modelName);
        root.set("state", state);
        root.set("questions", questions);
        return root;
    }

    private boolean isTemporary(int status) {
        return status == 408 || status == 429 || status >= 500;
    }

    /**
     * {@code detail} è un testo, un oggetto con {@code message} oppure un elenco di errori di
     * validazione. Di questi non si legge {@code input}, che ripete parte della richiesta.
     */
    private String errorMessage(String body) {
        try {
            JsonNode detail = mapper.readTree(body).path("detail");
            if (detail.isTextual()) return detail.asText();
            if (detail.has("message")) return detail.path("message").asText();
            if (detail.has(0)) {
                return detail.path(0).path("msg").asText() + " " + detail.path(0).path("loc");
            }
            return "risposta senza dettagli";
        } catch (IOException e) {
            return "risposta non JSON";
        }
    }
}
