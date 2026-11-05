package it.unical.uniticket;

import it.unical.uniticket.catalog.Catalog;
import it.unical.uniticket.catalog.CatalogBuilder;
import it.unical.uniticket.catalog.Category;
import it.unical.uniticket.dialog.ChatBot;
import it.unical.uniticket.dialog.ChatSession;
import it.unical.uniticket.dialog.DecisionPolicy;
import it.unical.uniticket.dialog.Reply;
import it.unical.uniticket.estimate.Estimate;
import it.unical.uniticket.estimate.Estimator;
import it.unical.uniticket.estimate.JevEstimator;
import it.unical.uniticket.estimate.Turn;
import it.unical.uniticket.search.FallbackSearch;
import it.unical.uniticket.search.HybridSearch;
import it.unical.uniticket.search.LexicalSearch;
import it.unical.uniticket.search.Search;
import it.unical.uniticket.search.SemanticSearch;
import it.unical.uniticket.web.Sessions;
import it.unical.uniticket.web.WebServer;
import it.unical.uniticket.web.WidgetApi;
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Duration;
import java.time.ZoneOffset;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Riga di comando. Comandi:
 * <pre>
 * chat            la chat (default); --debug mostra ricerca, stima e decisione di ogni turno
 * eval            misura il bot su eval/cases.json; --split dev|test|all, --out file.json
 * build-catalog   rigenera data/catalog.json da raw_cache
 * serve           il servizio HTTP per il widget di uniTicket; --port (default 8001)
 * </pre>
 * Il modello è Jev e serve {@code TYPESAFE_API_KEY}. Ollama si trova in {@code OLLAMA_URL} (default
 * localhost). Opzioni comuni ai comandi:
 * <pre>
 * --search hybrid|semantic|lexical   la ricerca (default hybrid); semantic ripiega su BM25 se Ollama
 *                                    cade; --lexical-only equivale a --search lexical
 * --shortlist N                      quanti candidati vede il modello (default 50)
 * </pre>
 */
public final class Main {

    private static final Path CATALOG = Path.of("data/catalog.json");
    private static final String OLLAMA_URL = System.getenv().getOrDefault("OLLAMA_URL", "http://localhost:11434");
    private static final String JEV_MODEL = "jev-1.14.0";

    private Main() {
    }

    public static void main(String[] args) throws IOException {
        // Lucene avvisa che non usa le Vector API: riguarda indici vettoriali che qui non ci sono.
        Logger.getLogger("org.apache.lucene.internal.vectorization").setLevel(Level.SEVERE);
        System.setOut(new PrintStream(System.out, true, StandardCharsets.UTF_8));
        String command = args.length > 0 && !args[0].startsWith("--") ? args[0] : "chat";
        Map<String, String> options = options(args);

        switch (command) {
            case "build-catalog" -> System.out.println(
                    CatalogBuilder.run(Path.of("raw_cache"), Path.of("data/structures-extra.json"), CATALOG));
            case "chat" -> chat(options);
            case "eval" -> eval(options);
            case "serve" -> serve(options);
            default -> {
                System.err.println("Comando sconosciuto: " + command + ". Comandi: chat, eval, build-catalog, serve");
                System.exit(2);
            }
        }
    }

    private static void chat(Map<String, String> options) throws IOException {
        Catalog catalog = Catalog.load(CATALOG);
        Estimator estimator = estimator(catalog);
        ChatBot bot = new ChatBot(catalog, search(options, catalog), estimator,
                new DecisionPolicy(DecisionPolicy.Params.DEFAULT), Clock.systemUTC(), shortlist(options));
        ChatSession session = new ChatSession();
        boolean debug = options.containsKey("debug");

        System.out.println("Modello: " + estimator.name());
        System.out.println("Ciao! Dimmi cosa ti serve e cerco il modulo giusto su uniTicket.");
        System.out.println("(/nuova per una nuova richiesta, /esci per uscire)");
        BufferedReader in = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
        while (true) {
            System.out.print("\nTu> ");
            String line = in.readLine();
            if (line == null || line.strip().equals("/esci")) {
                return;
            }
            if (line.strip().equals("/nuova")) {
                session.reset();
                System.out.println("Va bene, ricominciamo. Cosa ti serve?");
            } else if (!line.isBlank()) {
                Reply reply = bot.reply(session, line);
                if (debug) {
                    reply.trace().forEach(System.out::println);
                    System.out.println();
                }
                System.out.println("Bot> " + reply.text());
            }
        }
    }

    /**
     * La data è fissata a quella dello scrape: le etichette dei casi si riferiscono a quel giorno, e
     * un form scaduto dopo non deve contare come errore.
     */
    private static void eval(Map<String, String> options) {
        Catalog catalog = Catalog.load(CATALOG);
        Estimator estimator = estimator(catalog);
        Search search = search(options, catalog);
        DecisionPolicy policy = new DecisionPolicy(DecisionPolicy.Params.DEFAULT);
        Clock clock = Clock.fixed(catalog.fetchedAt(), ZoneOffset.UTC);
        int shortlist = shortlist(options);
        String out = options.get("out");
        Evaluation.run(
                Evaluation.load(Path.of(options.getOrDefault("cases", "eval/cases.json")),
                        options.getOrDefault("split", "dev"), Integer.parseInt(options.getOrDefault("limit", "0"))),
                new ChatBot(catalog, search, estimator, policy, clock, shortlist),
                estimator.name() + ", ricerca " + search.name() + ", " + shortlist + " candidati",
                out == null ? null : Path.of(out));
    }

    /**
     * Il servizio per il widget. Senza chiave di Jev parte lo stesso: ogni messaggio riceve i
     * risultati della sola ricerca, così il resto di docker-compose non dipende dalla chiave.
     */
    private static void serve(Map<String, String> options) throws IOException {
        Catalog catalog = Catalog.load(CATALOG);
        String key = System.getenv("TYPESAFE_API_KEY");
        Estimator estimator = key == null || key.isBlank() ? withoutModel() : new JevEstimator(catalog, key, JEV_MODEL);
        ChatBot bot = new ChatBot(catalog, search(options, catalog), estimator,
                new DecisionPolicy(DecisionPolicy.Params.DEFAULT), Clock.systemUTC(), shortlist(options));
        Sessions sessions = new Sessions(Duration.ofMinutes(30), 10_000, Clock.systemUTC());
        int port = Integer.parseInt(options.getOrDefault("port", "8001"));
        new WebServer(new WidgetApi(catalog, bot, sessions), "0.0.0.0", port).start();
        System.out.println("Servizio per il widget su :" + port + " (modello: " + estimator.name() + ")");
    }

    private static Estimator withoutModel() {
        System.err.println("TYPESAFE_API_KEY non impostata: rispondo con i soli risultati della ricerca.");
        return new Estimator() {
            @Override
            public Estimate estimate(List<Turn> conversation, List<Category> candidates) {
                throw new Http.ServiceException("TYPESAFE_API_KEY non impostata");
            }

            @Override
            public String name() {
                return "nessun modello";
            }
        };
    }

    /**
     * Jev, in una versione precisa: un alias come {@code jev-latest} potrebbe cambiare modello sotto
     * le misure. Senza chiave il bot si ferma e lo dice.
     */
    private static Estimator estimator(Catalog catalog) {
        String key = System.getenv("TYPESAFE_API_KEY");
        if (key == null || key.isBlank()) {
            System.err.println("Serve la variabile TYPESAFE_API_KEY con la chiave di Jev.");
            System.exit(2);
        }
        return new JevEstimator(catalog, key, JEV_MODEL);
    }

    /**
     * La ricerca scelta con {@code --search}: ibrida (default), solo semantica o solo BM25. Se Ollama
     * non c'è all'avvio resta BM25; se cade dopo, ibrida e semantica ripiegano su BM25 da sole.
     */
    private static Search search(Map<String, String> options, Catalog catalog) {
        Search lexical = new LexicalSearch(catalog);
        String kind = options.containsKey("lexical-only") ? "lexical" : options.getOrDefault("search", "hybrid");
        if (!List.of("hybrid", "semantic", "lexical").contains(kind)) {
            System.err.println("Ricerca sconosciuta: " + kind + ". Valori: hybrid, semantic, lexical");
            System.exit(2);
        }
        if (kind.equals("lexical")) {
            return lexical;
        }
        SemanticSearch semantic;
        try {
            semantic = new SemanticSearch(catalog, OLLAMA_URL, Path.of("data/cache"));
        } catch (Http.ServiceException e) {
            System.err.println("Embedding non disponibili (" + e.getMessage() + "): uso solo BM25.");
            return lexical;
        }
        return kind.equals("semantic") ? new FallbackSearch(semantic, lexical) : new HybridSearch(lexical, semantic);
    }

    /** {@code --shortlist N}: quanti candidati vede il modello. */
    private static int shortlist(Map<String, String> options) {
        String value = options.getOrDefault("shortlist", String.valueOf(ChatBot.DEFAULT_SHORTLIST));
        try {
            int n = Integer.parseInt(value);
            if (n >= 1) {
                return n;
            }
        } catch (NumberFormatException e) {
            // sotto
        }
        System.err.println("--shortlist vuole un intero positivo, non: " + value);
        System.exit(2);
        return 0;
    }

    /** {@code --nome valore} e {@code --flag}. */
    private static Map<String, String> options(String[] args) {
        Map<String, String> options = new HashMap<>();
        for (int i = 0; i < args.length; i++) {
            if (args[i].startsWith("--")) {
                boolean hasValue = i + 1 < args.length && !args[i + 1].startsWith("--");
                options.put(args[i].substring(2), hasValue ? args[++i] : "");
            }
        }
        return options;
    }
}
