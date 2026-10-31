package it.unical.uniticket.routing;

import it.unical.uniticket.api.dto.CategoryFormSchema;
import it.unical.uniticket.rag.UniTicketRagEngine.ScoredCategory;

import java.util.ArrayList;
import java.util.List;

/**
 * Esito della classificazione di una richiesta uniTicket.
 */
public class RoutingDecision {
    public static final String SELECT = "SELECT";
    public static final String CLARIFY = "CLARIFY";
    public static final String NONE = "NONE";

    public String action;
    public String selectedCompositeSlug = NONE;
    /** Probabilità calibrata del decisore; null se non disponibile. */
    public Double confidence;
    public String reasoning = "";
    public String clarifyingQuestion = "";
    public CategoryFormSchema matchedSchema;
    /** Motivo per cui il modulo scelto non è compilabile; vuoto se è aperto. */
    public String closureReason = "";
    /** True se il dipartimento è stato dedotto dal login e non dal testo della richiesta. */
    public boolean departmentFromProfile;
    /** Varianti di altri dipartimenti, per chi scrive per conto di un'altra struttura. */
    public List<CategoryFormSchema> otherDepartmentVariants = new ArrayList<>();
    /** True se la pratica è individuata con affidabilità: resta da scegliere al più la struttura. */
    public boolean settled;
    /** True se la ricerca è stata estesa ai moduli chiusi. */
    public boolean searchedClosedForms;
    public List<ScoredCategory> ragCandidates = new ArrayList<>();
    /** Opzioni da proporre in caso di CLARIFY. */
    public List<ScoredCategory> clarifyOptions = new ArrayList<>();

    public boolean isClosedForm() {
        return SELECT.equals(action) && !closureReason.isEmpty();
    }
}
