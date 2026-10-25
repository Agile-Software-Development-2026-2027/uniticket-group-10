package it.unical.uniticket.llm;

import java.util.List;

public interface EmbeddingClient {
    float[] embed(String text);

    List<float[]> embedBatch(List<String> texts);
}
