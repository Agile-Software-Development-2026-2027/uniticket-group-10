package it.unical.uniticket.routing;

import it.unical.uniticket.access.UserProfile;
import it.unical.uniticket.rag.UniTicketRagEngine.ScoredCategory;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/** Ciò che resta noto tra un turno di chiarimento e il successivo. */
public final class ConversationState {
    public final UserProfile profile;
    public final Set<String> rejectedSlugs = new HashSet<>();
    private String cumulativeQuery;
    private List<ScoredCategory> lastOptions = new ArrayList<>();

    public ConversationState(UserProfile profile, String initialRequest) {
        this.profile = profile;
        this.cumulativeQuery = initialRequest;
    }

    public String cumulativeQuery() {
        return cumulativeQuery;
    }

    public List<ScoredCategory> lastOptions() {
        return lastOptions;
    }

    void addReply(String reply) {
        cumulativeQuery = cumulativeQuery + "\n" + reply;
    }

    void remember(RoutingDecision decision) {
        lastOptions = new ArrayList<>(decision.clarifyOptions);
    }

    /** L'utente ha risposto che nessuna opzione mostrata è corretta. */
    public void rejectLastOptions() {
        for (ScoredCategory option : lastOptions) {
            option.groupVariants.forEach(variant -> rejectedSlugs.add(variant.compositeSlug));
            rejectedSlugs.add(option.schema.compositeSlug);
        }
    }
}
