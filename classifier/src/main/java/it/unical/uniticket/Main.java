package it.unical.uniticket;

import it.unical.uniticket.catalog.Catalog;
import it.unical.uniticket.catalog.CatalogBuilder;
import it.unical.uniticket.dialog.ChatBot;
import it.unical.uniticket.dialog.ChatSession;
import it.unical.uniticket.dialog.DecisionPolicy;
import it.unical.uniticket.dialog.Reply;
import it.unical.uniticket.estimate.Estimator;
import it.unical.uniticket.estimate.JevEstimator;
import it.unical.uniticket.search.HybridSearch;
import it.unical.uniticket.search.LexicalSearch;
import it.unical.uniticket.search.Search;
import it.unical.uniticket.search.SemanticSearch;
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Clock;
import java.time.ZoneOffset;
import java.util.HashMap;
import java.util.Map;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Riga di comando. Comandi:
 * <pre>
 * chat            la chat (default); --debug mostra ricerca, stima e decisione di ogni turno
 * eval            misura il bot su eval/cases.json; --split dev|test|all, --out file.json
 * build-catalog   rigenera data/catalog.json da raw_cache
 * </pre>
 * Il modello è Jev e serve {@code TYPESAFE_API_KEY}. Con {@code --lexical-only} si fa a meno di Ollama.
 */
public final class Main {

    private static final Path CATALOG = Path.of("data/catalog.json");
    private static final String OLLAMA_URL = "http://localhost:11434";
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
            default -> {
                System.err.println("Comando sconosciuto: " + command + ". Comandi: chat, eval, build-catalog");
                System.exit(2);
            }
        }
    }

    private static void chat(Map<String, String> options) throws IOException {
        Catalog catalog = Catalog.load(CATALOG);
        Estimator estimator = estimator(catalog);
        ChatBot bot = new ChatBot(catalog, search(options, catalog), estimator,
                new DecisionPolicy(DecisionPolicy.Params.DEFAULT), Clock.systemUTC());
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
        String out = options.get("out");
        Evaluation.run(
                Evaluation.load(Path.of(options.getOrDefault("cases", "eval/cases.json")),
                        options.getOrDefault("split", "dev"), Integer.parseInt(options.getOrDefault("limit", "0"))),
                new ChatBot(catalog, search, estimator, policy, clock),
                estimator.name(), out == null ? null : Path.of(out));
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

    /** Ricerca ibrida; se Ollama non c'è, solo BM25. */
    private static Search search(Map<String, String> options, Catalog catalog) {
        Search lexical = new LexicalSearch(catalog);
        if (options.containsKey("lexical-only")) {
            return lexical;
        }
        try {
            return new HybridSearch(lexical, new SemanticSearch(catalog, OLLAMA_URL, Path.of("data/cache")));
        } catch (Http.ServiceException e) {
            System.err.println("Embedding non disponibili (" + e.getMessage() + "): uso solo BM25.");
            return lexical;
        }
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
