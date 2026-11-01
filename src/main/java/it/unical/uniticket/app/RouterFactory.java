package it.unical.uniticket.app;

import it.unical.uniticket.llm.GeminiLlmClient;
import it.unical.uniticket.llm.LlmClient;
import it.unical.uniticket.llm.OllamaEmbeddingClient;
import it.unical.uniticket.llm.OllamaLlmClient;
import it.unical.uniticket.rag.UniTicketRagEngine;
import it.unical.uniticket.routing.FormRouter;
import it.unical.uniticket.routing.LlmFormDecider;

import java.io.File;
import java.io.IOException;

/**
 * Costruzione unica del router: applicazione e benchmark usano esattamente questa,
 * così ciò che si misura coincide con ciò che gira.
 */
public final class RouterFactory {
    public static final int DEFAULT_TOP_K = 8;

    private static final String OLLAMA_BASE_URL = setting("UNITICKET_OLLAMA_URL", "http://localhost:11434");
    private static final String LLM_PROVIDER = setting("UNITICKET_LLM_PROVIDER", "ollama");
    private static final String EMBEDDING_MODEL = setting("UNITICKET_EMBEDDING_MODEL", "bge-m3");

    private RouterFactory() {
    }

    public static UniTicketRagEngine createEngine(File catalogFile, File phrasesFile) throws IOException {
        // Una cache per configurazione, così confrontare varianti non invalida quella principale.
        String variant = phrasesFile != null && phrasesFile.isFile() ? "" : "-no-phrases";
        File cache = new File(".cache/uniticket-" + EMBEDDING_MODEL + variant + "-embeddings.json");
        return new UniTicketRagEngine(catalogFile,
                new OllamaEmbeddingClient(OLLAMA_BASE_URL, EMBEDDING_MODEL), cache, phrasesFile);
    }

    public static FormRouter createRouter(UniTicketRagEngine engine, int topK) {
        return new FormRouter(engine, new LlmFormDecider(createLlmClient()), topK);
    }

    /** Il provider cambia solo il decisore: la ricerca resta su Ollama, così soglie e ranking non si muovono. */
    private static LlmClient createLlmClient() {
        if ("gemini".equalsIgnoreCase(LLM_PROVIDER)) {
            String model = setting("UNITICKET_LLM_MODEL", "gemini-3.5-flash");
            LlmClient client = new GeminiLlmClient(System.getenv("GEMINI_API_KEY"), model);
            logDecider("Gemini", model);
            return client;
        }
        if ("ollama".equalsIgnoreCase(LLM_PROVIDER)) {
            String model = setting("UNITICKET_LLM_MODEL", "qwen2.5:3b");
            LlmClient client = new OllamaLlmClient(OLLAMA_BASE_URL + "/api/chat", model);
            logDecider("Ollama", model);
            return client;
        }
        throw new IllegalArgumentException("UNITICKET_LLM_PROVIDER sconosciuto: " + LLM_PROVIDER);
    }

    private static void logDecider(String provider, String model) {
        System.out.println("🧠 Modello decisore: " + provider + " (" + model + ")");
    }

    private static String setting(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.trim().isEmpty() ? fallback : value.trim();
    }
}
