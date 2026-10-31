package it.unical.uniticket.routing;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * Giudizio di pertinenza su un elenco di candidati. Esprime solo quale modulo
 * corrisponde alla richiesta: disponibilità e dipartimento spettano a {@link RoutingPolicy}.
 */
public final class DeciderVerdict {
    public static final int NO_MATCH = -1;

    /** Indice del candidato migliore, oppure {@link #NO_MATCH}. */
    public final int bestIndex;
    /** Altri candidati che la richiesta non permette di distinguere da quello migliore. */
    public final List<Integer> alternatives;
    /** Probabilità calibrata; null se il modello non ne fornisce una affidabile. */
    public final Double confidence;
    public final String reasoning;
    public final String clarifyingQuestion;
    /** True se il modello non ha prodotto una risposta utilizzabile. */
    public final boolean failed;

    private DeciderVerdict(int bestIndex, List<Integer> alternatives, Double confidence,
                           String reasoning, String clarifyingQuestion, boolean failed) {
        this.bestIndex = bestIndex;
        this.alternatives = Collections.unmodifiableList(new ArrayList<>(alternatives));
        this.confidence = confidence;
        this.reasoning = reasoning == null ? "" : reasoning;
        this.clarifyingQuestion = clarifyingQuestion == null ? "" : clarifyingQuestion;
        this.failed = failed;
    }

    public static DeciderVerdict match(int bestIndex, List<Integer> alternatives, Double confidence,
                                       String reasoning, String clarifyingQuestion) {
        return new DeciderVerdict(bestIndex, alternatives, confidence, reasoning,
                clarifyingQuestion, false);
    }

    public static DeciderVerdict noMatch(String reasoning) {
        return new DeciderVerdict(NO_MATCH, Collections.emptyList(), null, reasoning, "", false);
    }

    public static DeciderVerdict failed(String reasoning) {
        return new DeciderVerdict(NO_MATCH, Collections.emptyList(), null, reasoning, "", true);
    }
}
