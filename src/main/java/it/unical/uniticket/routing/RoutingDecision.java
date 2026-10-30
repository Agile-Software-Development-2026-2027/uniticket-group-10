package it.unical.uniticket.routing;

import it.unical.uniticket.api.dto.CategoryFormSchema;
import it.unical.uniticket.rag.UniTicketRagEngine.ScoredCategory;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * Esito della classificazione di una richiesta uniTicket.
 */
public class RoutingDecision {
    public String action;
    public String selectedCompositeSlug;
    public double confidence;
    public String reasoning;
    public String clarifyingQuestion;
    public CategoryFormSchema matchedSchema;
    public List<ScoredCategory> ragCandidates = new ArrayList<>();
    /** Candidati dichiarati plausibili direttamente dal router LLM. */
    public List<ScoredCategory> plausibleCandidates = new ArrayList<>();
    /** Candidati plausibili e accessibili da proporre in caso di CLARIFY. */
    public List<ScoredCategory> clarifyOptions = new ArrayList<>();
    /** Slug scartati esplicitamente dall'utente durante la sessione. */
    public Set<String> rejectedSlugs = new HashSet<>();
    /** Query completa usata per l'ultimo turno di retrieval. */
    public String cumulativeQuery;
}
