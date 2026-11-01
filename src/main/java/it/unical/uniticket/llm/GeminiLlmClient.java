package it.unical.uniticket.llm;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.jsoup.Connection;
import org.jsoup.Jsoup;

import java.io.IOException;

/**
 * Client per la Gemini API. Le richieste escono dalla macchina: con utenti reali nello Spazio
 * economico europeo i termini di Google ammettono solo il piano a pagamento.
 *
 * <p>La chiave viaggia in un header, così non finisce mai negli URL o nei messaggi di errore.</p>
 */
public class GeminiLlmClient implements LlmClient {
    private static final String BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models/";
    private static final int TIMEOUT_MILLIS = 120_000;
    private static final int MAX_ATTEMPTS = 6;
    private static final long FIRST_RETRY_MILLIS = 2_000;

    private final String apiKey;
    private final String modelName;
    private final ObjectMapper mapper = new ObjectMapper();

    public GeminiLlmClient(String apiKey, String modelName) {
        if (apiKey == null || apiKey.trim().isEmpty()) {
            throw new IllegalArgumentException("Per usare Gemini serve la variabile GEMINI_API_KEY.");
        }
        this.apiKey = apiKey.trim();
        this.modelName = modelName;
    }

    @Override
    public String generate(String systemPrompt, String userPrompt) {
        return generate(systemPrompt, userPrompt, null);
    }

    @Override
    public String generate(String systemPrompt, String userPrompt, JsonNode responseSchema) {
        try {
            String body = mapper.writeValueAsString(buildRequest(systemPrompt, userPrompt, responseSchema));
            long wait = FIRST_RETRY_MILLIS;
            for (int attempt = 1; ; attempt++) {
                Connection.Response response = post(body);
                if (response.statusCode() == 200) return extractText(mapper.readTree(response.body()));
                if (attempt == MAX_ATTEMPTS || !isTemporary(response.statusCode())) {
                    throw new IllegalStateException("HTTP " + response.statusCode() + ": "
                            + errorMessage(response.body()));
                }
                Thread.sleep(wait);
                wait *= 2;
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new RuntimeException("Chiamata Gemini interrotta.", e);
        } catch (IOException | IllegalStateException e) {
            throw new RuntimeException("Errore chiamata Gemini con il modello '" + modelName + "': "
                    + e.getMessage(), e);
        }
    }

    private Connection.Response post(String body) throws IOException {
        return Jsoup.connect(BASE_URL + modelName + ":generateContent")
                .header("Content-Type", "application/json")
                .header("x-goog-api-key", apiKey)
                .requestBody(body)
                .ignoreContentType(true)
                .ignoreHttpErrors(true)
                .timeout(TIMEOUT_MILLIS)
                .method(Connection.Method.POST)
                .execute();
    }

    ObjectNode buildRequest(String systemPrompt, String userPrompt, JsonNode responseSchema) {
        ObjectNode root = mapper.createObjectNode();
        root.putObject("systemInstruction").putArray("parts").addObject().put("text", systemPrompt);
        ObjectNode userMessage = root.putArray("contents").addObject();
        userMessage.put("role", "user");
        userMessage.putArray("parts").addObject().put("text", userPrompt);

        ObjectNode config = root.putObject("generationConfig");
        config.put("temperature", 0.0);
        config.put("seed", 42);
        config.put("responseMimeType", "application/json");
        if (responseSchema != null) config.set("responseJsonSchema", responseSchema);
        return root;
    }

    String extractText(JsonNode reply) {
        JsonNode candidate = reply.path("candidates").path(0);
        StringBuilder text = new StringBuilder();
        for (JsonNode part : candidate.path("content").path("parts")) {
            text.append(part.path("text").asText(""));
        }
        if (text.length() == 0) {
            throw new IllegalStateException("risposta senza testo, finishReason="
                    + candidate.path("finishReason").asText("assente"));
        }
        return text.toString();
    }

    private boolean isTemporary(int status) {
        return status == 429 || status == 500 || status == 503 || status == 504;
    }

    private String errorMessage(String body) {
        try {
            return mapper.readTree(body).path("error").path("message").asText("risposta senza dettagli");
        } catch (IOException e) {
            return "risposta non JSON";
        }
    }
}
