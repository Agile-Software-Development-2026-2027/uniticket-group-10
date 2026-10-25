package it.unical.uniticket.routing;

import it.unical.uniticket.api.dto.CategoryFormSchema;
import it.unical.uniticket.rag.UniTicketRagEngine.ScoredCategory;

import java.util.ArrayList;
import java.util.List;

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
    /** Candidati plausibili e accessibili da proporre in caso di CLARIFY. */
    public List<ScoredCategory> clarifyOptions = new ArrayList<>();
}
