package it.unical.uniticket.routing;

import it.unical.uniticket.access.UserProfile;
import it.unical.uniticket.rag.UniTicketRagEngine.ScoredCategory;

import java.util.List;

/**
 * Sceglie tra i candidati del retrieval. È l'unico punto che dipende dal modello:
 * per passare da Ollama a JEV o a un altro servizio basta una nuova implementazione.
 */
public interface FormDecider {
    DeciderVerdict decide(String request, List<ScoredCategory> candidates, UserProfile profile);

    /** Nome da mostrare a chi legge la traccia, con il modello se è noto. */
    default String name() {
        return getClass().getSimpleName();
    }
}
