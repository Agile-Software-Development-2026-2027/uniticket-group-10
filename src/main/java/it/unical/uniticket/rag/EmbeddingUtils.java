package it.unical.uniticket.rag;

public final class EmbeddingUtils {
    private EmbeddingUtils() {
    }

    public static double cosine(float[] a, float[] b) {
        if (a == null || b == null || a.length == 0 || b.length != a.length) return 0.0;
        double dot = 0.0;
        double normA = 0.0;
        double normB = 0.0;
        for (int i = 0; i < a.length; i++) {
            dot += a[i] * b[i];
            normA += a[i] * a[i];
            normB += b[i] * b[i];
        }
        if (normA == 0.0 || normB == 0.0) return 0.0;
        return dot / (Math.sqrt(normA) * Math.sqrt(normB));
    }
}
