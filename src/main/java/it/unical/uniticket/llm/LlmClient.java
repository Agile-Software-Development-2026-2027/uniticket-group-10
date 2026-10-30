package it.unical.uniticket.llm;

import com.fasterxml.jackson.databind.JsonNode;

@FunctionalInterface
public interface LlmClient {
    String generate(String systemPrompt, String userPrompt);

    default String generate(String systemPrompt, String userPrompt, JsonNode responseSchema) {
        return generate(systemPrompt, userPrompt);
    }
}
