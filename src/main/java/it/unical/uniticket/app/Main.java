package it.unical.uniticket.app;

import it.unical.uniticket.access.FormAccess;
import it.unical.uniticket.access.UserProfile;
import it.unical.uniticket.api.dto.CategoryFormSchema;
import it.unical.uniticket.rag.UniTicketRagEngine;
import it.unical.uniticket.rag.UniTicketRagEngine.ScoredCategory;
import it.unical.uniticket.routing.ConversationState;
import it.unical.uniticket.routing.FormRouter;
import it.unical.uniticket.routing.RoutingDecision;

import java.io.File;
import java.util.List;
import java.util.Locale;
import java.util.Scanner;

/**
 * CLI di prova. Argomenti opzionali, che simulano il login:
 * {@code --role student|staff} e {@code --department <slug struttura>}.
 */
public class Main {
    private static final int MAX_TURNS = 3;

    public static void main(String[] args) throws Exception {
        File catalogFile = new File("uniticket.json");
        if (!catalogFile.exists()) {
            System.err.println("❌ File uniticket.json non trovato in: " + catalogFile.getAbsolutePath());
            return;
        }
        UserProfile profile = parseProfile(args);

        System.out.println("⏳ Inizializzazione motore RAG (BM25 + embeddings)...");
        UniTicketRagEngine engine = RouterFactory.createEngine(catalogFile, new File("form_phrases.json"));
        FormRouter router = RouterFactory.createRouter(engine, RouterFactory.DEFAULT_TOP_K);

        Scanner scanner = new Scanner(System.in);
        System.out.println("==================================================================");
        System.out.println("🤖 UNITICKET AI AGENT - PROVA DRY-RUN (NESSUN INVIO REALE)");
        System.out.println("==================================================================");
        System.out.print("\n💬 Descrivi il tuo problema: ");
        String request = scanner.hasNextLine() ? scanner.nextLine().trim() : "";
        if (request.isEmpty()) return;

        ConversationState state = new ConversationState(profile, request);
        RoutingDecision decision = router.route(state);
        for (int turn = 1; turn < MAX_TURNS && RoutingDecision.CLARIFY.equals(decision.action); turn++) {
            printOptions(decision, profile);
            System.out.print("\n💬 Precisazione: ");
            String reply = scanner.hasNextLine() ? scanner.nextLine().trim() : "";
            if (reply.isEmpty()) {
                System.out.println("Nessuna precisazione fornita. Sessione annullata.");
                return;
            }
            decision = nextDecision(reply, decision.clarifyOptions, state, router);
        }
        printOutcome(decision);
    }

    private static RoutingDecision nextDecision(String reply, List<ScoredCategory> options,
                                                ConversationState state, FormRouter router) {
        if ("0".equals(reply) || reply.equalsIgnoreCase("nessuno")
                || reply.equalsIgnoreCase("nessuno di questi")) {
            state.rejectLastOptions();
            return router.refine("Nessuna delle opzioni precedenti è pertinente.", state);
        }
        if (reply.matches("\\d{1,9}")) {
            int index = Integer.parseInt(reply) - 1;
            if (index >= 0 && index < options.size()) return router.pick(options.get(index), state);
        }
        return router.refine(reply, state);
    }

    private static UserProfile parseProfile(String[] args) {
        UserProfile.Role role = UserProfile.Role.UNKNOWN;
        String department = null;
        for (int i = 0; i + 1 < args.length; i += 2) {
            if ("--role".equals(args[i])) {
                role = UserProfile.Role.valueOf(args[i + 1].toUpperCase(Locale.ROOT));
            } else if ("--department".equals(args[i])) {
                department = args[i + 1];
            }
        }
        return UserProfile.of(role, department);
    }

    private static void printOptions(RoutingDecision decision, UserProfile profile) {
        System.out.println("\n❓ " + decision.clarifyingQuestion);
        for (int i = 0; i < decision.clarifyOptions.size(); i++) {
            ScoredCategory option = decision.clarifyOptions.get(i);
            String status = FormAccess.of(option.schema, profile) == FormAccess.OPEN
                    ? "" : " (al momento non disponibile)";
            System.out.printf("   %d) [%s] %s%s%n", i + 1,
                    option.schema.structureName, option.schema.categoryTitle, status);
        }
        System.out.println("   0) Nessuna di queste");
    }

    private static void printOutcome(RoutingDecision decision) {
        if (RoutingDecision.CLARIFY.equals(decision.action)) {
            System.out.println("\n❌ Non sono riuscito a individuare il modulo: rivolgiti all'URP.");
            return;
        }
        if (!RoutingDecision.SELECT.equals(decision.action)) {
            System.out.println("\n❌ Nessun modulo uniTicket compatibile con la tua richiesta.");
            return;
        }
        CategoryFormSchema form = decision.matchedSchema;
        System.out.println("\n==================================================================");
        System.out.println(decision.isClosedForm() ? "⚠️ MODULO INDIVIDUATO, MA NON DISPONIBILE"
                : "✅ CLASSIFICAZIONE COMPLETATA");
        System.out.println("==================================================================");
        System.out.println("Struttura : " + form.structureName);
        System.out.println("Tipologia : " + form.categoryTitle);
        if (decision.isClosedForm()) {
            System.out.println("Stato     : " + decision.closureReason);
        } else if (FormAccess.isRoleRestricted(form)) {
            System.out.println("Stato     : riservato al personale, campi del modulo non verificati");
        } else {
            System.out.println("Stato     : attivo");
        }
        if (decision.departmentFromProfile && !decision.otherDepartmentVariants.isEmpty()) {
            System.out.println("Ho usato il dipartimento del tuo profilo. Se la richiesta è per un'altra "
                    + "struttura, puoi scegliere anche:");
            decision.otherDepartmentVariants.forEach(variant ->
                    System.out.println("   - " + variant.structureName));
        }
    }
}
