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
    private final RoutingTrace trace;

    public FormRouter(UniTicketRagEngine ragEngine, FormDecider decider, int topK) {
        this(ragEngine, decider, topK, RoutingTrace.SILENT);
    }

    public FormRouter(UniTicketRagEngine ragEngine, FormDecider decider, int topK, RoutingTrace trace) {
        this.ragEngine = ragEngine;
        this.decider = decider;
        this.topK = topK;
        this.trace = trace;
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
        if (RoutingDecision.SELECT.equals(decision.action)) {
            decision.decidedBy = RoutingDecision.DecidedBy.USER;
            decision.rule = ("Indicato dall'utente tra le opzioni proposte. " + decision.rule).trim();
        }
        state.remember(decision);
        trace.decided(decision, decider.name());
        return decision;
    }

    private RoutingDecision decide(String query, ConversationState state) {
        Set<String> rejected = Collections.unmodifiableSet(state.rejectedSlugs);
        List<ScoredCategory> openForms = ragEngine.searchOpen(query, topK, state.profile, rejected);
        trace.searched(openForms, false);
        RoutingDecision decision = decideAmong(query, openForms, state.profile);
        List<ScoredCategory> allForms = ragEngine.search(query, topK, state.profile, rejected);
        trace.searched(allForms, true);
        if (decision.settled) {
            decision = policy.reviewAgainstClosedForms(decision, allForms, state.profile);
        } else {
            RoutingDecision widened = decideAmong(query, allForms, state.profile);
            if (!RoutingDecision.NONE.equals(widened.action)) decision = widened;
            decision.searchedClosedForms = true;
        }
        state.remember(decision);
        trace.decided(decision, decider.name());
        return decision;
    }

    private RoutingDecision decideAmong(String query, List<ScoredCategory> candidates, UserProfile profile) {
        if (candidates.isEmpty()) {
            return policy.apply(query, candidates,
                    DeciderVerdict.noMatch("Nessun modulo compatibile nel catalogo."), profile);
        }
        DeciderVerdict verdict = decider.decide(query, candidates, profile);
        trace.judged(decider.name(), candidates, verdict);
        return policy.apply(query, candidates, verdict, profile);
    }
}
