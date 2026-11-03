package it.unical.uniticket.web;

import it.unical.uniticket.catalog.Catalog;
import it.unical.uniticket.dialog.Reply;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Le frasi del widget, in italiano e in inglese. I moduli compaiono come card, quindi qui non si
 * elencano. Le frasi su aiuto alla compilazione e richieste non trovate sono quelle di {@code agent/}.
 */
final class WidgetTexts {

    private static final WidgetTexts ITALIAN = new WidgetTexts(false);
    private static final WidgetTexts ENGLISH = new WidgetTexts(true);

    /** Le domande fisse di DecisionPolicy, tradotte. */
    private static final Map<String, String> QUESTIONS_EN = Map.of(
            "A quale corso di studi o dipartimento fai riferimento?",
            "Which degree course or department are you referring to?",
            "Quale di questi corrisponde alla tua richiesta?", "Which of these matches your request?",
            "Puoi darmi qualche dettaglio in più?", "Could you give me a few more details?");

    private final boolean english;

    private WidgetTexts(boolean english) {
        this.english = english;
    }

    /** L'inglese per "en", "en-us" e simili; l'italiano per tutto il resto. */
    static WidgetTexts of(String language) {
        return language.toLowerCase(Locale.ROOT).startsWith("en") ? ENGLISH : ITALIAN;
    }

    String reply(Reply reply, Catalog catalog) {
        boolean withOptions = !reply.options().isEmpty();
        return switch (reply.kind()) {
            case SELECTED -> t("Ecco la richiesta che fa al caso tuo. Se non è quella giusta, scrivimi \"no\".",
                    "Here is the request you need. If it is not the right one, write \"no\".");
            case CONFIRMED -> t("Perfetto, ecco la richiesta.", "Great, here is the request.");
            case CONFIRM_STRUCTURE -> {
                String structure = catalog.structureOf(reply.options().get(0)).label();
                yield t("Ho trovato questa richiesta, ma è del " + structure
                                + ". Fa al caso tuo? Se no, dimmi il tuo corso di studi o la tua struttura.",
                        "I found this request, but it belongs to " + structure
                                + ". Is it right for you? If not, tell me your degree course or your office.");
            }
            case CLARIFY -> {
                String question = english ? QUESTIONS_EN.getOrDefault(reply.question(), reply.question())
                        : reply.question();
                yield withOptions ? question + t(" Puoi anche aprire direttamente una di queste richieste.",
                        " You can also open one of these requests directly.") : question;
            }
            case SHORTLIST -> t("Non riesco a restringere oltre. Queste sono le richieste più vicine: apri quella giusta.",
                    "I cannot narrow it down further. These are the closest requests: open the right one.");
            case NO_MATCH -> t("Non ho trovato richieste adatte. Prova a indicare il servizio o il documento di cui hai bisogno.",
                    "No suitable requests found. Try specifying the service or document you need.");
            case DEGRADED -> withOptions
                    ? t("Al momento non riesco a ragionare sulla richiesta. Ecco cosa ho trovato nel catalogo.",
                            "I cannot reason about the request right now. Here is what I found in the catalog.")
                    : t("Al momento non riesco a elaborare la richiesta, riprova tra poco.",
                            "I cannot process the request right now, please try again shortly.");
        };
    }

    /** Si inviano come messaggi: "sì" e "no" sono risposte chiuse, il bot le capisce senza modello. */
    List<String> confirmSuggestions() {
        return english ? List.of("Yes", "No") : List.of("Sì", "No");
    }

    String offerHelp(String form) {
        return english ? "Would you like help filling out the request “" + form + "”?"
                : "Vuoi aiuto a compilare la richiesta «" + form + "»?";
    }

    String helpLabel() {
        return t("Aiutami a compilare questa richiesta", "Help me fill out this request");
    }

    String startHelp() {
        return t("Ti aiuto a compilare la richiesta. Da quale campo vuoi partire?",
                "I can help you fill out the request. Which field would you like to start with?");
    }

    String notFound() {
        return t("Domanda non trovata o scaduta.", "Question not found or expired.");
    }

    private String t(String italian, String englishText) {
        return english ? englishText : italian;
    }
}
