package it.unical.uniticket.routing;

import it.unical.uniticket.access.FormAccess;
import it.unical.uniticket.access.UserProfile;
import it.unical.uniticket.api.dto.CategoryFormSchema;
import it.unical.uniticket.rag.UniTicketRagEngine.ScoredCategory;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;

/**
 * Trasforma un giudizio di pertinenza in un'azione. Tutto qui è deterministico:
 * non chiama modelli, quindi le regole si possono verificare con test unitari.
 */
public class RoutingPolicy {
    private static final int MAX_OPTIONS = 4;
    private static final int FALLBACK_OPTIONS = 3;
    /**
     * Il modello locale è sempre sicuro di sé, quindi la selezione diretta richiede che anche
     * la ricerca concordi. Soglie tarate sui set di sviluppo: dipendono dal modello di
     * embedding e dalle frasi indicizzate, quindi vanno riviste se questi cambiano.
     */
    static final double SELECT_MIN_SIMILARITY = 0.55;
    /** Oltre questa posizione la scelta del modello smentisce la ricerca. */
    static final int SELECT_MAX_RANK = 3;
    /**
     * Sopra questa soglia un "nessun modulo" del modello diventa una richiesta di conferma:
     * sui set di sviluppo le richieste davvero fuori tema restano tutte al di sotto.
     */
    static final double NONE_REVIEW_SIMILARITY = 0.60;
    /** Da tarare quando un decisore fornirà probabilità calibrate (ad esempio JEV). */
    static final double SELECT_MIN_CONFIDENCE = 0.70;
    private static final String DEFAULT_QUESTION = "Quale di queste opzioni descrive meglio la tua richiesta?";

    public RoutingDecision apply(String query, List<ScoredCategory> candidates,
                                 DeciderVerdict verdict, UserProfile profile) {
        RoutingDecision decision;
        if (candidates.isEmpty()) {
            decision = none("Nessun modulo compatibile nel catalogo.");
        } else if (verdict.failed) {
            decision = clarify(candidates.subList(0, Math.min(FALLBACK_OPTIONS, candidates.size())),
                    DEFAULT_QUESTION, verdict.reasoning);
        } else if (verdict.bestIndex == DeciderVerdict.NO_MATCH) {
            decision = candidates.get(0).embeddingScore >= NONE_REVIEW_SIMILARITY
                    ? clarify(candidates.subList(0, Math.min(FALLBACK_OPTIONS, candidates.size())),
                            DEFAULT_QUESTION, verdict.reasoning)
                    : none(verdict.reasoning);
        } else if (canSelect(candidates, verdict)) {
            decision = resolvePractice(query, candidates.get(verdict.bestIndex), profile);
            decision.reasoning = verdict.reasoning;
            decision.settled = true;
        } else {
            decision = clarifyBetweenPractices(candidates, verdict);
        }
        decision.confidence = verdict.confidence;
        decision.ragCandidates = new ArrayList<>(candidates);
        return decision;
    }

    private boolean canSelect(List<ScoredCategory> candidates, DeciderVerdict verdict) {
        if (!verdict.alternatives.isEmpty()) return false;
        if (verdict.confidence != null) return verdict.confidence >= SELECT_MIN_CONFIDENCE;
        return verdict.bestIndex < SELECT_MAX_RANK
                && candidates.get(verdict.bestIndex).embeddingScore >= SELECT_MIN_SIMILARITY;
    }

    /**
     * Una selezione aperta si conferma solo se nessun modulo chiuso la supera: quando il primo
     * risultato sull'intero catalogo è chiuso e simile almeno quanto la scelta, l'utente vede
     * entrambi. Evita di mandare in silenzio su un modulo aperto chi cerca una pratica chiusa.
     */
    public RoutingDecision reviewAgainstClosedForms(RoutingDecision decision,
                                                    List<ScoredCategory> allForms, UserProfile profile) {
        if (!RoutingDecision.SELECT.equals(decision.action) || decision.isClosedForm()
                || allForms.isEmpty()) {
            return decision;
        }
        ScoredCategory top = allForms.get(0);
        ScoredCategory pick = decision.ragCandidates.stream()
                .filter(candidate -> candidate.groupVariants.contains(decision.matchedSchema))
                .findFirst()
                .orElse(null);
        boolean challenged = pick != null
                && FormAccess.of(top.schema, profile) == FormAccess.CLOSED
                && !pick.groupVariants.contains(top.schema)
                && top.embeddingScore >= pick.embeddingScore;
        if (!challenged) return decision;
        RoutingDecision review = clarify(Arrays.asList(pick, top), DEFAULT_QUESTION, decision.reasoning);
        review.confidence = decision.confidence;
        review.ragCandidates = decision.ragCandidates;
        return review;
    }

    /**
     * Sceglie la variante di una pratica già individuata. Vince la struttura nominata nel
     * testo, poi quella del login; se nessuna delle due decide, si chiede all'utente.
     */
    public RoutingDecision resolvePractice(String query, ScoredCategory practice, UserProfile profile) {
        List<CategoryFormSchema> variants = practice.groupVariants.isEmpty()
                ? java.util.Collections.singletonList(practice.schema) : practice.groupVariants;
        if (variants.size() == 1) return select(variants.get(0), practice, profile);

        List<CategoryFormSchema> named = DepartmentMatcher.named(query, variants);
        if (named.size() == 1) return select(named.get(0), practice, profile);

        List<CategoryFormSchema> own = variants.stream()
                .filter(variant -> profile.belongsTo(variant.structureSlug))
                .collect(Collectors.toList());
        if (named.isEmpty() && !own.isEmpty()) {
            CategoryFormSchema chosen = preferOpen(own, profile);
            RoutingDecision decision = select(chosen, practice, profile);
            decision.departmentFromProfile = true;
            decision.otherDepartmentVariants = variants.stream()
                    .filter(variant -> !own.contains(variant))
                    .filter(variant -> FormAccess.of(variant, profile) == FormAccess.OPEN)
                    .collect(Collectors.toList());
            return decision;
        }
        List<CategoryFormSchema> choices = named.isEmpty() ? variants : named;
        return clarify(asOptions(choices, practice, profile),
                "A quale dipartimento o struttura si riferisce la tua richiesta?",
                "La pratica esiste in più strutture e il testo non indica quale.");
    }

    private RoutingDecision clarifyBetweenPractices(List<ScoredCategory> candidates,
                                                    DeciderVerdict verdict) {
        List<ScoredCategory> options = new ArrayList<>();
        options.add(candidates.get(verdict.bestIndex));
        verdict.alternatives.stream().limit(MAX_OPTIONS - 1L)
                .forEach(index -> options.add(candidates.get(index)));
        // Senza alternative la domanda nasce da una scelta poco affidabile: si completa
        // l'elenco con i risultati migliori della ricerca.
        if (verdict.alternatives.isEmpty()) {
            for (ScoredCategory candidate : candidates) {
                if (options.size() == MAX_OPTIONS) break;
                if (!options.contains(candidate)) options.add(candidate);
            }
        }
        String question = verdict.clarifyingQuestion.trim().isEmpty()
                ? DEFAULT_QUESTION : verdict.clarifyingQuestion;
        return clarify(options, question, verdict.reasoning);
    }

    private CategoryFormSchema preferOpen(List<CategoryFormSchema> forms, UserProfile profile) {
        return forms.stream()
                .filter(form -> FormAccess.of(form, profile) == FormAccess.OPEN)
                .findFirst()
                .orElse(forms.get(0));
    }

    private List<ScoredCategory> asOptions(List<CategoryFormSchema> variants, ScoredCategory practice,
                                           UserProfile profile) {
        return variants.stream()
                .sorted(Comparator.comparing(variant -> FormAccess.of(variant, profile)))
                .map(variant -> new ScoredCategory(variant, practice.score))
                .collect(Collectors.toList());
    }

    private RoutingDecision select(CategoryFormSchema form, ScoredCategory practice, UserProfile profile) {
        RoutingDecision decision = new RoutingDecision();
        decision.action = RoutingDecision.SELECT;
        decision.selectedCompositeSlug = form.compositeSlug;
        decision.matchedSchema = form;
        if (FormAccess.of(form, profile) != FormAccess.OPEN) {
            String reason = FormAccess.closureReason(form);
            decision.closureReason = reason.isEmpty() ? "Il modulo non è attualmente attivo." : reason;
        }
        return decision;
    }

    private RoutingDecision clarify(List<ScoredCategory> options, String question, String reasoning) {
        RoutingDecision decision = new RoutingDecision();
        decision.action = RoutingDecision.CLARIFY;
        decision.clarifyOptions = new ArrayList<>(options);
        decision.clarifyingQuestion = question;
        decision.reasoning = reasoning;
        return decision;
    }

    private RoutingDecision none(String reasoning) {
        RoutingDecision decision = new RoutingDecision();
        decision.action = RoutingDecision.NONE;
        decision.reasoning = reasoning;
        return decision;
    }
}
