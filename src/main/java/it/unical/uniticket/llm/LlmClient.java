package it.unical.uniticket.llm;

@FunctionalInterface
public interface LlmClient {
    String generate(String systemPrompt, String userPrompt);
}
