package it.unical.uniticket.app;

import it.unical.uniticket.llm.OllamaEmbeddingClient;
import it.unical.uniticket.llm.OllamaLlmClient;
import it.unical.uniticket.rag.UniTicketRagEngine;
import it.unical.uniticket.routing.FormRouter;
import it.unical.uniticket.routing.OllamaFormDecider;

import java.io.File;
import java.io.IOException;

/**
 * Costruzione unica del router: applicazione e benchmark usano esattamente questa,
 * così ciò che si misura coincide con ciò che gira.
 */
public final class RouterFactory {
    public static final int DEFAULT_TOP_K = 8;

    private static final String OLLAMA_BASE_URL = setting("UNITICKET_OLLAMA_URL", "http://localhost:11434");
    private static final String LLM_MODEL = setting("UNITICKET_LLM_MODEL", "qwen2.5:3b");
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
        return new FormRouter(engine,
                new OllamaFormDecider(new OllamaLlmClient(OLLAMA_BASE_URL + "/api/chat", LLM_MODEL)),
                topK);
    }

    private static String setting(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.trim().isEmpty() ? fallback : value.trim();
    }
}
