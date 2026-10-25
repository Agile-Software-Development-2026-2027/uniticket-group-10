package it.unical.uniticket.llm;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.jsoup.Connection;
import org.jsoup.Jsoup;

public class OllamaLlmClient implements LlmClient {
    private final String ollamaUrl;
    private final String modelName;
    private final ObjectMapper mapper = new ObjectMapper();

    public OllamaLlmClient(String ollamaUrl, String modelName) {
        this.ollamaUrl = ollamaUrl;
        this.modelName = modelName;
    }

    @Override
    public String generate(String systemPrompt, String userPrompt) {
        try {
            ObjectNode root = mapper.createObjectNode();
            root.put("model", modelName);
            root.put("stream", false);
            root.put("format", "json");

            ObjectNode options = root.putObject("options");
            options.put("temperature", 0.0);
            options.put("num_ctx", 4096);
            options.put("num_predict", 512);

            ArrayNode messages = root.putArray("messages");
            messages.addObject().put("role", "system").put("content", systemPrompt);
            messages.addObject().put("role", "user").put("content", userPrompt);

            Connection.Response response = Jsoup.connect(ollamaUrl)
                    .header("Content-Type", "application/json")
                    .requestBody(mapper.writeValueAsString(root))
                    .ignoreContentType(true)
                    .timeout(60_000)
                    .method(Connection.Method.POST)
                    .execute();

            JsonNode responseJson = mapper.readTree(response.body());
            return responseJson.path("message").path("content").asText("{}");
        } catch (Exception e) {
            throw new RuntimeException("Errore chiamata Ollama su " + ollamaUrl
                    + " (verifica che 'ollama serve' sia attivo e il modello '" + modelName + "' sia installato): "
                    + e.getMessage(), e);
        }
    }
}
