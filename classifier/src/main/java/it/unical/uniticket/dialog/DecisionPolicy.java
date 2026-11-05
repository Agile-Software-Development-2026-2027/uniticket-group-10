package it.unical.uniticket.dialog;

import it.unical.uniticket.catalog.Category;
import it.unical.uniticket.estimate.Estimate;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.stream.Collectors;

/**
 * Trasforma la stima del modello in una decisione. È codice deterministico: si testa senza
 * modello e si tara sui dati.
 *
 * <p><b>Una sola regola.</b> Si ordinano le ipotesi (moduli, "nessun modulo", "servono
 * informazioni") dalla più probabile e si prende il più piccolo gruppo la cui quota cumulata
 * raggiunge la confidenza richiesta (0,8). Se nel gruppo c'è un solo modulo il bot è sicuro; se ci
 * sono più ipotesi chiede; se resta solo "nessun modulo" lo dice. È l'idea dei <i>prediction
 * set</i> per decidere quando chiedere aiuto (KnowNo, arXiv:2307.01928), costruiti in modo
 * cumulato come negli <i>adaptive prediction sets</i> (arXiv:2006.02544).
 *
 * <p>Conta la quota cumulata, non la soglia sulla singola ipotesi: con 34% al primo modulo e tanti
 * 11% dietro, una soglia al 20% vedrebbe un solo candidato e lo darebbe per certo.
 *
 * <p><b>La trappola dei dipartimenti.</b> Più della metà dei moduli è di un solo dipartimento: uno
 * studente di Fisica che chiede un attestato di frequenza finirebbe, con piena sicurezza del
 * modello, sul modulo del DiBEST. Quindi un modulo di dipartimento non è mai una certezza finché
 * la conversazione non indica quella struttura: il bot chiede conferma.
 */
public final class DecisionPolicy {

    private static final String ASK_STRUCTURE = "A quale corso di studi o dipartimento fai riferimento?";
    private static final String ASK_WHICH = "Quale di questi corrisponde alla tua richiesta?";
    private static final String ASK_DETAILS = "Puoi darmi qualche dettaglio in più?";

    /**
     * @param confidence   quota cumulata che il gruppo di ipotesi deve raggiungere
     * @param maxOptions   moduli mostrati al massimo all'utente
     * @param maxQuestions domande oltre le quali non si insiste
     */
    public record Params(double confidence, int maxOptions, int maxQuestions) {
        public static final Params DEFAULT = new Params(0.8, 5, 3);
    }

    public sealed interface Decision {
    }

    /** Un solo modulo credibile. */
    public record Selected(Category category) implements Decision {
    }

    /** Un solo modulo, ma di un dipartimento che l'utente non ha indicato: va confermato. */
    public record ConfirmStructure(Category category) implements Decision {
    }

    /** Incertezza: una domanda, con i candidati come opzioni (possono mancare). */
    public record Clarify(String question, List<Category> options) implements Decision {
    }

    /** Domande esaurite: si mostrano i candidati migliori e sceglie l'utente. */
    public record Shortlist(List<Category> options) implements Decision {
    }

    /** Nessun modulo adatto. */
    public record NoMatch() implements Decision {
    }

    /** Un'ipotesi: un modulo, oppure (category null) "nessun modulo" o "servono informazioni". */
    private record Hypothesis(Category category, double share, boolean noMatch) {

        String describe() {
            String name = category != null ? category.name() : noMatch ? "nessun modulo" : "servono informazioni";
            return name + " " + percent(share);
        }
    }

    private final Params params;

    public DecisionPolicy(Params params) {
        this.params = params;
    }

    public Decision decide(Estimate estimate, int questionsAsked) {
        List<Hypothesis> set = predictionSet(estimate);
        if (set.size() == 1) {
            Hypothesis only = set.get(0);
            if (only.category() != null) {
                return certain(only.category(), estimate.structure(), questionsAsked);
            }
            if (only.noMatch()) {
                return new NoMatch();
            }
        }
        List<Category> options = set.stream().map(Hypothesis::category).filter(c -> c != null)
                .limit(params.maxOptions()).toList();
        if (questionsAsked >= params.maxQuestions()) {
            return options.isEmpty() ? new NoMatch() : new Shortlist(options);
        }
        return new Clarify(question(options), options);
    }

    /** Un modulo di dipartimento è certo solo se la struttura (verificata) è proprio quella. */
    private Decision certain(Category category, String userStructure, int questionsAsked) {
        if (!category.departmental() || category.structure().equals(userStructure)) {
            return new Selected(category);
        }
        return questionsAsked >= params.maxQuestions() ? new Shortlist(List.of(category)) : new ConfirmStructure(category);
    }

    private List<Hypothesis> predictionSet(Estimate estimate) {
        List<Hypothesis> hypotheses = new ArrayList<>();
        estimate.forms().forEach(f -> hypotheses.add(new Hypothesis(f.category(), f.share(), false)));
        hypotheses.add(new Hypothesis(null, estimate.noMatch(), true));
        hypotheses.add(new Hypothesis(null, estimate.needsInfo(), false));
        hypotheses.sort(Comparator.comparingDouble(Hypothesis::share).reversed());

        List<Hypothesis> set = new ArrayList<>();
        double cumulative = 0;
        for (Hypothesis hypothesis : hypotheses) {
            if (cumulative >= params.confidence() || hypothesis.share() <= 0) {
                break;
            }
            set.add(hypothesis);
            cumulative += hypothesis.share();
        }
        return set;
    }

    /** Una domanda fissa (Jev non scrive testo): moduli di più dipartimenti vogliono dire che manca il "dove". */
    private static String question(List<Category> options) {
        if (options.isEmpty()) {
            return ASK_DETAILS;
        }
        long departments = options.stream().filter(Category::departmental).map(Category::structure).distinct().count();
        return departments > 1 ? ASK_STRUCTURE : ASK_WHICH;
    }

    /** Perché si è arrivati a questa decisione, per la traccia del turno. */
    public String explain(Estimate estimate, Decision decision) {
        List<Hypothesis> set = predictionSet(estimate);
        return "Ipotesi fino al " + percent(params.confidence()) + ": "
                + set.stream().map(Hypothesis::describe).collect(Collectors.joining(", "))
                + " → " + decision.getClass().getSimpleName();
    }

    static String percent(double share) {
        return String.format(Locale.ITALIAN, "%.0f%%", share * 100);
    }
}
