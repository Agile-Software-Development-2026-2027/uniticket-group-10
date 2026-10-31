package it.unical.uniticket.routing;

import it.unical.uniticket.access.UserProfile;
import it.unical.uniticket.api.dto.CategoryFormSchema;
import it.unical.uniticket.rag.UniTicketRagEngine;
import it.unical.uniticket.rag.UniTicketRagEngine.ScoredCategory;

import java.util.Collections;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * Coordina i tre passi della classificazione: ricerca, giudizio di pertinenza, regole.
 *
 * <p>La ricerca considera prima i soli moduli aperti. Quelli chiusi entrano in gioco se
 * nessun modulo aperto corrisponde in modo affidabile, oppure se uno di loro supera nettamente
 * la scelta: in quel caso l'utente vede entrambi.</p>
 */
public class FormRouter {
    private final UniTicketRagEngine ragEngine;
    private final FormDecider decider;
    private final RoutingPolicy policy = new RoutingPolicy();
    private final int topK;

    public FormRouter(UniTicketRagEngine ragEngine, FormDecider decider, int topK) {
        this.ragEngine = ragEngine;
        this.decider = decider;
        this.topK = topK;
    }

    /** Primo turno della conversazione. */
    public RoutingDecision route(ConversationState state) {
        return decide(state.cumulativeQuery(), state);
    }

    /** Turno successivo in cui l'utente ha scritto una precisazione. */
    public RoutingDecision refine(String reply, ConversationState state) {
        state.addReply(reply);
        List<CategoryFormSchema> shown = state.lastOptions().stream()
                .flatMap(option -> option.groupVariants.stream())
                .collect(Collectors.toList());
        List<CategoryFormSchema> named = DepartmentMatcher.named(reply, shown);
        if (named.size() == 1) {
            return pick(new ScoredCategory(named.get(0), 0.0), state);
        }
        return decide(state.cumulativeQuery(), state);
    }

    /** L'utente ha scelto una delle opzioni numerate. */
    public RoutingDecision pick(ScoredCategory option, ConversationState state) {
        RoutingDecision decision = policy.resolvePractice(
                state.cumulativeQuery(), option, state.profile);
        state.remember(decision);
        return decision;
    }

    private RoutingDecision decide(String query, ConversationState state) {
        Set<String> rejected = Collections.unmodifiableSet(state.rejectedSlugs);
        RoutingDecision decision = decideAmong(query,
                ragEngine.searchOpen(query, topK, state.profile, rejected), state.profile);
        List<ScoredCategory> allForms = ragEngine.search(query, topK, state.profile, rejected);
        if (decision.settled) {
            decision = policy.reviewAgainstClosedForms(decision, allForms, state.profile);
        } else {
            RoutingDecision widened = decideAmong(query, allForms, state.profile);
            if (!RoutingDecision.NONE.equals(widened.action)) decision = widened;
            decision.searchedClosedForms = true;
        }
        state.remember(decision);
        return decision;
    }

    private RoutingDecision decideAmong(String query, List<ScoredCategory> candidates, UserProfile profile) {
        DeciderVerdict verdict = candidates.isEmpty()
                ? DeciderVerdict.noMatch("Nessun modulo compatibile nel catalogo.")
                : decider.decide(query, candidates, profile);
        return policy.apply(query, candidates, verdict, profile);
    }
}
