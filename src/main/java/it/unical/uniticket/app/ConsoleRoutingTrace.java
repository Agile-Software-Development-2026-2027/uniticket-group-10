package it.unical.uniticket.app;

import it.unical.uniticket.access.FormAccess;
import it.unical.uniticket.access.UserProfile;
import it.unical.uniticket.api.dto.CategoryFormSchema;
import it.unical.uniticket.rag.UniTicketRagEngine.ScoredCategory;
import it.unical.uniticket.routing.DeciderVerdict;
import it.unical.uniticket.routing.RoutingDecision;
import it.unical.uniticket.routing.RoutingTrace;

import java.io.PrintStream;
import java.util.List;
import java.util.Locale;
import java.util.stream.Collectors;

/** Stampa i passi della classificazione, per vedere chi ha deciso cosa. */
final class ConsoleRoutingTrace implements RoutingTrace {
    private final PrintStream out;
    private final UserProfile profile;

    ConsoleRoutingTrace(PrintStream out, UserProfile profile) {
        this.out = out;
        this.profile = profile;
    }

    @Override
    public void searched(List<ScoredCategory> candidates, boolean closedFormsIncluded) {
        String scope = closedFormsIncluded ? "su tutto il catalogo, moduli chiusi compresi" : "tra i moduli aperti";
        out.println("\n🔎 Top " + candidates.size() + " " + scope);
        if (candidates.isEmpty()) return;
        out.println("    #      RRF  Simil.    BM25  Stato   Modulo");
        for (int i = 0; i < candidates.size(); i++) {
            ScoredCategory candidate = candidates.get(i);
            out.printf(Locale.ROOT, "   %2d  %7.4f  %6.3f  %6.2f  %-6s  %s%n", i + 1, candidate.score,
                    candidate.embeddingScore, candidate.bm25Score, status(candidate), label(candidate));
        }
    }

    @Override
    public void judged(String deciderName, List<ScoredCategory> candidates, DeciderVerdict verdict) {
        out.println("\n🧠 Giudizio del decisore " + deciderName);
        out.println("   Scelta      : " + choice(candidates, verdict));
        if (!verdict.alternatives.isEmpty()) {
            out.println("   Alternative : " + verdict.alternatives.stream()
                    .map(index -> "#" + (index + 1))
                    .collect(Collectors.joining(", ")));
        }
        if (verdict.confidence != null) {
            out.printf(Locale.ROOT, "   Confidenza  : %.2f%n", verdict.confidence);
        }
        if (!verdict.reasoning.isEmpty()) out.println("   Motivo      : " + verdict.reasoning);
    }

    @Override
    public void decided(RoutingDecision decision, String deciderName) {
        out.println("\n⚖️  Decisione: " + outcome(decision));
        out.println("   Deciso da : " + author(decision, deciderName));
        if (!decision.rule.isEmpty()) out.println("   Motivo    : " + decision.rule);
    }

    private String choice(List<ScoredCategory> candidates, DeciderVerdict verdict) {
        if (verdict.failed) return "nessuna risposta utilizzabile";
        if (verdict.bestIndex == DeciderVerdict.NO_MATCH) return "nessun modulo pertinente";
        return "#" + (verdict.bestIndex + 1) + " " + label(candidates.get(verdict.bestIndex));
    }

    private String outcome(RoutingDecision decision) {
        if (RoutingDecision.SELECT.equals(decision.action)) {
            return "modulo selezionato, " + label(decision.matchedSchema);
        }
        return RoutingDecision.CLARIFY.equals(decision.action) ? "domanda all'utente" : "nessun modulo";
    }

    private String author(RoutingDecision decision, String deciderName) {
        switch (decision.decidedBy) {
            case DECIDER:
                return deciderName;
            case USER:
                return "utente";
            default:
                return "regole deterministiche (RoutingPolicy)";
        }
    }

    private String status(ScoredCategory candidate) {
        return FormAccess.of(candidate.schema, profile) == FormAccess.OPEN ? "aperto" : "chiuso";
    }

    private String label(ScoredCategory candidate) {
        int others = candidate.groupVariants.size() - 1;
        return label(candidate.schema) + (others > 0 ? " (+" + others + " strutture)" : "");
    }

    private String label(CategoryFormSchema form) {
        return "[" + form.structureName + "] " + form.categoryTitle;
    }
}
