package it.unical.uniticket;

import com.fasterxml.jackson.core.type.TypeReference;
import it.unical.uniticket.catalog.Category;
import it.unical.uniticket.dialog.ChatBot;
import it.unical.uniticket.dialog.ChatSession;
import it.unical.uniticket.dialog.Reply;
import it.unical.uniticket.dialog.Reply.Kind;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;

/**
 * Misura il bot sui casi di {@code eval/cases.json}.
 *
 * <p><b>Primo turno</b>: cosa fa il bot con il solo primo messaggio. L'errore grave è la selezione
 * sbagliata, perché l'utente non ha modo di accorgersene; una domanda in più costa poco.
 *
 * <p><b>Dialogo</b>: un utente "a copione", senza LLM. Se tra le opzioni c'è il modulo giusto ne
 * sceglie il numero; altrimenti, una sola volta, risponde con la frase {@code persona} del caso
 * (es. "Iscritta a Biologia."); poi si arrende.
 */
final class Evaluation {

    /** Un caso di prova. {@code expect}: single, ask o none; per none, {@code gold} elenca esiti tollerati. */
    record Case(String id, String split, String group, String expect, String text, List<String> gold,
                String persona) {

        boolean expectsNone() {
            return "none".equals(expect);
        }

        boolean isGold(Category category) {
            return gold.contains(category.id());
        }
    }

    private static final int MAX_TURNS = 4;

    private Evaluation() {
    }

    static List<Case> load(Path file, String split, int limit) {
        List<Case> cases = Json.MAPPER.convertValue(Json.read(file), new TypeReference<List<Case>>() {
        }).stream().filter(c -> "all".equals(split) || c.split().equals(split)).toList();
        return limit > 0 ? cases.subList(0, Math.min(limit, cases.size())) : cases;
    }

    static void run(List<Case> cases, ChatBot bot, String model, Path out) {
        Map<String, Integer> first = new LinkedHashMap<>();
        for (String key : List.of("selezioni giuste", "selezioni sbagliate", "domande con il modulo giusto",
                "domande senza il modulo giusto", "nessun modulo, giusto", "nessun modulo, a torto", "errori del modello")) {
            first.put(key, 0);
        }
        Map<String, Map<String, Integer>> dialogues = new TreeMap<>();
        List<Map<String, Object>> details = new ArrayList<>();
        int goldCases = 0;

        for (int i = 0; i < cases.size(); i++) {
            Case c = cases.get(i);
            System.err.printf("\r%d/%d %s   ", i + 1, cases.size(), c.id());
            goldCases += c.expectsNone() ? 0 : 1;
            ChatSession session = new ChatSession();
            List<String> log = new ArrayList<>();
            Reply reply = say(bot, session, c.text(), log);
            String firstOutcome = firstTurn(c, reply);
            first.merge(firstOutcome, 1, Integer::sum);

            boolean personaUsed = false;
            for (int turn = 1; turn < MAX_TURNS && !reply.isFinal() && reply.kind() != Kind.DEGRADED; turn++) {
                int gold = indexOfGold(reply.options(), c);
                if (gold >= 0) {
                    reply = say(bot, session, Integer.toString(gold + 1), log);
                } else if (c.persona() != null && !personaUsed && reply.kind() != Kind.SHORTLIST) {
                    personaUsed = true;
                    reply = say(bot, session, c.persona(), log);
                } else {
                    break;
                }
            }
            String outcome = dialogueOutcome(c, reply);
            dialogues.computeIfAbsent(c.group(), g -> new TreeMap<>()).merge(outcome, 1, Integer::sum);

            Map<String, Object> row = new LinkedHashMap<>();
            row.put("id", c.id());
            row.put("group", c.group());
            row.put("gold", c.gold());
            row.put("firstTurn", firstOutcome);
            row.put("dialogue", outcome);
            row.put("log", log);
            details.add(row);
        }
        System.err.println();
        print(model, cases.size(), goldCases, first, dialogues);
        if (out != null) {
            Json.writePretty(out, Map.of("model", model, "firstTurn", first, "dialogues", dialogues, "cases", details));
            System.out.println("Dettaglio dei casi in " + out);
        }
    }

    private static Reply say(ChatBot bot, ChatSession session, String text, List<String> log) {
        Reply reply = bot.reply(session, text);
        log.add("U: " + text);
        log.add("B: " + reply.kind() + " " + reply.options().stream().map(Category::id).toList());
        return reply;
    }

    private static String firstTurn(Case c, Reply reply) {
        return switch (reply.kind()) {
            case SELECTED -> c.isGold(reply.options().get(0))
                    ? (c.expectsNone() ? "nessun modulo, giusto" : "selezioni giuste") : "selezioni sbagliate";
            case CONFIRM_STRUCTURE, CLARIFY, SHORTLIST -> indexOfGold(reply.options(), c) >= 0
                    ? "domande con il modulo giusto" : "domande senza il modulo giusto";
            case NO_MATCH -> c.expectsNone() ? "nessun modulo, giusto" : "nessun modulo, a torto";
            case DEGRADED, CONFIRMED -> "errori del modello";
        };
    }

    private static String dialogueOutcome(Case c, Reply reply) {
        return switch (reply.kind()) {
            case SELECTED, CONFIRMED -> c.isGold(reply.options().get(0)) ? "giusto" : "sbagliato";
            case NO_MATCH -> c.expectsNone() ? "nessun modulo, giusto" : "nessun modulo, a torto";
            default -> "non risolto";
        };
    }

    private static int indexOfGold(List<Category> options, Case c) {
        for (int i = 0; i < options.size(); i++) {
            if (c.isGold(options.get(i))) {
                return i;
            }
        }
        return -1;
    }

    private static void print(String model, int cases, int goldCases, Map<String, Integer> first,
                              Map<String, Map<String, Integer>> dialogues) {
        System.out.printf("%nModello %s, %d casi%n%nPrimo turno:%n", model, cases);
        first.forEach((k, v) -> System.out.printf("  %-32s %4d%n", k, v));
        int right = first.get("selezioni giuste");
        int selected = right + first.get("selezioni sbagliate");
        System.out.printf(Locale.ITALIAN, "  Precisione delle selezioni: %.1f%% (%d su %d)%n",
                selected == 0 ? 0 : 100.0 * right / selected, right, selected);
        System.out.printf(Locale.ITALIAN, "  Modulo giusto scelto o tra le opzioni: %.1f%% (su %d casi con un modulo)%n",
                goldCases == 0 ? 0 : 100.0 * (right + first.get("domande con il modulo giusto")) / goldCases, goldCases);

        System.out.println("\nDialogo con l'utente a copione, per gruppo:");
        Map<String, Integer> total = new TreeMap<>();
        dialogues.forEach((group, outcomes) -> {
            System.out.printf("  %-16s %s%n", group, outcomes);
            outcomes.forEach((k, v) -> total.merge(k, v, Integer::sum));
        });
        System.out.printf("  %-16s %s%n", "TOTALE", total);
    }
}
