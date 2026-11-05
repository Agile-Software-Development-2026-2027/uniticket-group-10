package it.unical.uniticket.dialog;

import it.unical.uniticket.Http;
import it.unical.uniticket.catalog.Catalog;
import it.unical.uniticket.catalog.Category;
import it.unical.uniticket.dialog.DecisionPolicy.Clarify;
import it.unical.uniticket.dialog.DecisionPolicy.ConfirmStructure;
import it.unical.uniticket.dialog.DecisionPolicy.Decision;
import it.unical.uniticket.dialog.DecisionPolicy.NoMatch;
import it.unical.uniticket.dialog.DecisionPolicy.Selected;
import it.unical.uniticket.dialog.DecisionPolicy.Shortlist;
import it.unical.uniticket.dialog.Reply.Kind;
import it.unical.uniticket.estimate.Estimate;
import it.unical.uniticket.estimate.Estimator;
import it.unical.uniticket.estimate.Turn;
import it.unical.uniticket.search.Search;
import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.OptionalInt;
import java.util.Set;
import java.util.function.Predicate;
import java.util.stream.Collectors;

/**
 * La logica del dialogo. Ogni messaggio dell'utente passa per gli stessi passi:
 * <ol>
 *   <li>se è una risposta chiusa ("2", "sì") alla proposta precedente, si chiude lì;</li>
 *   <li><b>ricerca</b>: i moduli aperti più vicini a tutto ciò che l'utente ha scritto (20, salvo
 *       diversa indicazione);</li>
 *   <li><b>stima</b>: il modello distribuisce la probabilità tra quei moduli;</li>
 *   <li><b>verifica</b> della struttura riportata dal modello;</li>
 *   <li><b>decisione</b> con {@link DecisionPolicy} e risposta.</li>
 * </ol>
 * Il bot non ha stato: la conversazione, i moduli proposti e rifiutati e le domande fatte stanno in
 * una {@link ChatSession}, che il chiamante passa a ogni messaggio. Un solo bot serve quindi tutti
 * gli utenti, ciascuno con la sua sessione.
 */
public final class ChatBot {

    /**
     * Quanti candidati vede il modello, se non si indica altro. Con {@code bge-m3} il modulo giusto è
     * tra i primi 20 nel 98% dei casi; nell'eval con Jev 20 candidati valgono quanto 50, con meno
     * della metà delle domande per chiamata.
     */
    public static final int DEFAULT_SHORTLIST = 20;
    private static final int DEGRADED_OPTIONS = 3;
    private static final int MAX_MESSAGE_CHARS = 2000;

    private final Catalog catalog;
    private final Search search;
    private final Estimator estimator;
    private final DecisionPolicy policy;
    private final Clock clock;
    private final int shortlist;

    public ChatBot(Catalog catalog, Search search, Estimator estimator, DecisionPolicy policy,
                   Clock clock) {
        this(catalog, search, estimator, policy, clock, DEFAULT_SHORTLIST);
    }

    /** Con {@code shortlist} candidati per il modello: meno candidati, meno domande a ogni stima. */
    public ChatBot(Catalog catalog, Search search, Estimator estimator, DecisionPolicy policy,
                   Clock clock, int shortlist) {
        if (shortlist < 1) {
            throw new IllegalArgumentException("Serve almeno un candidato, non " + shortlist);
        }
        this.catalog = catalog;
        this.search = search;
        this.estimator = estimator;
        this.policy = policy;
        this.clock = clock;
        this.shortlist = shortlist;
    }

    /** Risponde a un messaggio dell'utente e aggiorna la sua sessione. */
    public Reply reply(ChatSession session, String message) {
        return reply(session, message, category -> true);
    }

    /**
     * Come {@link #reply(ChatSession, String)}, con i soli moduli che {@code allowed} accetta tra i
     * candidati: nel portale, quelli che l'utente collegato può aprire.
     */
    public Reply reply(ChatSession session, String message, Predicate<Category> allowed) {
        if (session.isClosed()) {
            session.reset();
        }
        String text = message.strip();
        text = text.length() > MAX_MESSAGE_CHARS ? text.substring(0, MAX_MESSAGE_CHARS) : text;

        // 1. Risposte chiuse: nessuna ricerca e nessun modello.
        List<Category> proposed = session.proposed();
        if (!proposed.isEmpty()) {
            OptionalInt choice = UserChoice.parse(text, proposed.size());
            if (choice.isPresent()) {
                return confirm(session, text, proposed.get(choice.getAsInt()));
            }
            if (proposed.size() == 1 && UserChoice.isAcceptance(text)) {
                return confirm(session, text, proposed.get(0));
            }
        }
        session.addUser(text);
        if (UserChoice.isRejection(text)) {
            session.rejectProposed();
        }

        // 2. Ricerca: si cerca tutto ciò che ha scritto l'utente, ogni risposta aggiunge contesto.
        List<Turn> conversation = session.conversation();
        String query = conversation.stream().filter(Turn::fromUser).map(Turn::text).collect(Collectors.joining(". "));
        List<String> trace = new ArrayList<>();
        List<Category> candidates = candidates(session, query, allowed, trace);

        // 3. Stima del modello.
        Estimate estimate;
        long start = System.nanoTime();
        try {
            estimate = estimator.estimate(conversation, candidates);
        } catch (Http.ServiceException e) {
            return degraded(session, candidates, e.getMessage(), trace);
        }
        trace.add("[" + estimator.name() + ", " + (System.nanoTime() - start) / 1_000_000 + " ms]");
        estimate.forms().stream().limit(8).forEach(f ->
                trace.add("  " + DecisionPolicy.percent(f.share()) + "  " + f.category().name()
                        + " (" + f.category().structure() + ")"));
        trace.add("  " + DecisionPolicy.percent(estimate.noMatch()) + "  nessun modulo");
        trace.add("  " + DecisionPolicy.percent(estimate.needsInfo()) + "  servono informazioni");

        // 4. Verifica della struttura, 5. decisione.
        String verified = verifiedStructure(session, estimate.structure(), query);
        trace.add("[Verifica struttura] riportata: " + estimate.structure() + ", accettata: " + verified);
        estimate = estimate.withStructure(verified);
        Decision decision = policy.decide(estimate, session.questionsAsked());
        trace.add("[DecisionPolicy] " + policy.explain(estimate, decision));
        return apply(session, decision, trace);
    }

    /**
     * I moduli da mostrare al modello: prima quelli proposti al turno precedente (una risposta
     * breve come "sono di Fisica" non deve farli sparire), poi i migliori della ricerca, saltando
     * quelli rifiutati dall'utente e quelli chiusi in questo momento.
     */
    private List<Category> candidates(ChatSession session, String query, Predicate<Category> allowed,
                                      List<String> trace) {
        Instant now = clock.instant();
        Set<String> rejected = session.rejected();
        Map<String, Category> selected = new LinkedHashMap<>();
        session.proposed().stream().filter(c -> !rejected.contains(c.id()) && allowed.test(c))
                .forEach(c -> selected.put(c.id(), c));
        for (Search.Hit hit : search.search(query, shortlist + rejected.size() + 20)) {
            Category category = hit.category();
            if (selected.size() < shortlist && !rejected.contains(category.id()) && category.isOpenAt(now)
                    && allowed.test(category)) {
                selected.putIfAbsent(category.id(), category);
            }
        }
        List<Category> candidates = List.copyOf(selected.values());
        trace.add("[Ricerca " + search.name() + "] " + candidates.size() + " candidati, i primi:");
        candidates.stream().limit(5).forEach(c -> trace.add("  " + c.name() + " (" + c.structure() + ")"));
        return candidates;
    }

    /**
     * Il modello potrebbe dedurre la struttura dal modulo che gli sembra giusto, e così un modulo di
     * dipartimento risulterebbe certo per chiunque. Il dato vale solo con un riscontro: l'utente ha
     * nominato la struttura, oppure il bot gli ha appena proposto un solo modulo di quella struttura
     * (e l'utente ha risposto qualcosa come "certo, è quello").
     */
    private String verifiedStructure(ChatSession session, String reported, String query) {
        if (reported == null) {
            return null;
        }
        List<Category> proposed = session.proposed();
        boolean justProposed = proposed.size() == 1 && proposed.get(0).structure().equals(reported);
        return justProposed || catalog.structuresNamedIn(query).contains(reported) ? reported : null;
    }

    private Reply apply(ChatSession session, Decision decision, List<String> trace) {
        return switch (decision) {
            case Selected s -> {
                propose(session, List.of(s.category()), "Ho proposto il modulo: " + s.category().name());
                yield new Reply(Kind.SELECTED, "Il modulo che ti serve è:\n" + describe(s.category())
                        + "\nSe non è quello giusto, scrivimi \"no\".", session.proposed(), trace);
            }
            case ConfirmStructure c -> {
                session.countQuestion();
                propose(session, List.of(c.category()), "Ho chiesto se va bene il modulo \"" + c.category().name()
                        + "\", che è della struttura " + c.category().structure());
                yield new Reply(Kind.CONFIRM_STRUCTURE, "Ho trovato questo modulo, ma è del "
                        + catalog.structureOf(c.category()).label() + ". Fa al caso tuo?\n  " + c.category().name()
                        + "\nRispondi \"sì\", oppure dimmi la tua struttura o il tuo corso di studi.",
                        session.proposed(), trace);
            }
            case Clarify c -> {
                session.countQuestion();
                propose(session, c.options(), c.question() + optionNames(c.options()));
                yield new Reply(Kind.CLARIFY, c.question() + numbered(c.options()), c.question(), session.proposed(),
                        trace);
            }
            case Shortlist s -> {
                propose(session, s.options(), "Ho proposto questi moduli." + optionNames(s.options()));
                yield new Reply(Kind.SHORTLIST, "Non riesco a restringere oltre. Questi sono i moduli più vicini, "
                        + "rispondi con il numero di quello giusto:" + numbered(s.options()), session.proposed(), trace);
            }
            case NoMatch n -> {
                propose(session, List.of(), "Ho risposto che non esiste un modulo adatto.");
                yield new Reply(Kind.NO_MATCH, "Non ho trovato un modulo disponibile per questa richiesta.",
                        List.of(), trace);
            }
        };
    }

    /** Il modello non risponde: meglio i primi risultati della ricerca che nessuna risposta. */
    private Reply degraded(ChatSession session, List<Category> candidates, String failure, List<String> trace) {
        trace.add("[Modello non disponibile] " + failure);
        List<Category> options = candidates.stream().limit(DEGRADED_OPTIONS).toList();
        session.propose(options);
        String text = options.isEmpty() ? "Al momento non riesco a elaborare la richiesta, riprova tra poco."
                : "Al momento non riesco a ragionare sulla richiesta. Ho cercato nel catalogo: "
                        + "rispondi con il numero se uno di questi va bene." + numbered(options);
        return new Reply(Kind.DEGRADED, text, session.proposed(), trace);
    }

    private Reply confirm(ChatSession session, String text, Category category) {
        session.addUser(text);
        propose(session, List.of(category), "L'utente ha scelto il modulo: " + category.name());
        session.close();
        return new Reply(Kind.CONFIRMED, "Perfetto, ecco il modulo:\n" + describe(category), session.proposed(),
                List.of("[UserChoice] \"" + text + "\" sceglie " + category.id() + ": nessuna ricerca, nessun modello"));
    }

    /**
     * L'utente ha aperto un modulo senza scriverlo, per esempio con un clic su una proposta: vale
     * come una scelta, e il messaggio successivo è una richiesta nuova.
     */
    public void opened(ChatSession session, Category category) {
        if (session.isClosed()) {
            session.reset();
        }
        propose(session, List.of(category), "L'utente ha aperto il modulo: " + category.name());
        session.close();
    }

    /** Ricorda cosa ha proposto il bot, anche nella conversazione: così il modello capisce "la seconda". */
    private static void propose(ChatSession session, List<Category> options, String botTurn) {
        session.propose(options);
        session.addBot(botTurn);
    }

    private String describe(Category category) {
        return "  " + category.name() + " (" + catalog.structureOf(category).label() + ")\n  " + category.url();
    }

    private String numbered(List<Category> options) {
        StringBuilder list = new StringBuilder();
        for (int i = 0; i < options.size(); i++) {
            list.append("\n  ").append(i + 1).append(". ").append(options.get(i).name())
                    .append(" (").append(catalog.structureOf(options.get(i)).name()).append(')');
        }
        return list.toString();
    }

    private static String optionNames(List<Category> options) {
        return options.isEmpty() ? "" : " Opzioni proposte: "
                + options.stream().map(Category::name).collect(Collectors.joining("; "));
    }
}
