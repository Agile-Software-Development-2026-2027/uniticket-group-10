package it.unical.uniticket.app;

import it.unical.uniticket.access.UserProfile;
import it.unical.uniticket.api.dto.CategoryFormSchema;
import it.unical.uniticket.rag.UniTicketRagEngine.ScoredCategory;
import it.unical.uniticket.routing.DeciderVerdict;
import it.unical.uniticket.routing.RoutingDecision;
import junit.framework.TestCase;

import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class ConsoleRoutingTraceTest extends TestCase {
    private final ByteArrayOutputStream bytes = new ByteArrayOutputStream();
    private ConsoleRoutingTrace trace;

    @Override
    protected void setUp() throws Exception {
        trace = new ConsoleRoutingTrace(new PrintStream(bytes, true, "UTF-8"), UserProfile.unknown());
    }

    private static CategoryFormSchema form(String structure, String title, boolean open) {
        CategoryFormSchema form = new CategoryFormSchema();
        form.structureSlug = structure;
        form.structureName = structure.toUpperCase();
        form.categoryTitle = title;
        form.compositeSlug = structure + "__" + title;
        form.accessible = open;
        form.accessRestrictionReason = open ? null : "HTTP 404: modulo non attivo";
        return form;
    }

    private static ScoredCategory scored(double similarity, CategoryFormSchema... variants) {
        return new ScoredCategory(variants[0], 0.0325, 7.5, similarity, Arrays.asList(variants));
    }

    private String output() {
        return new String(bytes.toByteArray(), StandardCharsets.UTF_8);
    }

    public void testTopKShowsRankScoresStatusAndVariants() {
        List<ScoredCategory> candidates = Arrays.asList(
                scored(0.712, form("ict", "Wifi", true), form("dimes", "Wifi", true)),
                scored(0.401, form("ict", "Posta", false)));
        trace.searched(candidates, true);
        String text = output();
        assertTrue(text, text.contains("Top 2 su tutto il catalogo"));
        assertTrue(text, text.contains("1   0.0325   0.712    7.50  aperto  [ICT] Wifi (+1 strutture)"));
        assertTrue(text, text.contains("2   0.0325   0.401    7.50  chiuso  [ICT] Posta"));
    }

    public void testEmptySearchPrintsNoTable() {
        trace.searched(Collections.emptyList(), false);
        assertTrue(output(), output().contains("Top 0 tra i moduli aperti"));
        assertFalse(output(), output().contains("BM25"));
    }

    public void testVerdictUsesTheSameNumberingAsTopK() {
        List<ScoredCategory> candidates = Arrays.asList(scored(0.7, form("ict", "Wifi", true)),
                scored(0.6, form("ict", "Posta", true)), scored(0.5, form("ict", "Rete", true)));
        trace.judged("Ollama (m)", candidates,
                DeciderVerdict.match(1, Collections.singletonList(2), 0.83, "perché sì", ""));
        String text = output();
        assertTrue(text, text.contains("Giudizio del decisore Ollama (m)"));
        assertTrue(text, text.contains("#2 [ICT] Posta"));
        assertTrue(text, text.contains("#3"));
        assertTrue(text, text.contains("0.83"));
        assertTrue(text, text.contains("perché sì"));
    }

    public void testFailedVerdictIsNotShownAsNoMatch() {
        trace.judged("Gemini (m)", Collections.singletonList(scored(0.7, form("ict", "Wifi", true))),
                DeciderVerdict.failed("timeout"));
        assertTrue(output(), output().contains("nessuna risposta utilizzabile"));
        assertFalse(output(), output().contains("nessun modulo pertinente"));
    }

    public void testDecisionNamesTheDeciderOnlyWhenItDecided() {
        RoutingDecision decision = new RoutingDecision();
        decision.action = RoutingDecision.SELECT;
        decision.matchedSchema = form("ict", "Wifi", true);
        decision.decidedBy = RoutingDecision.DecidedBy.DECIDER;
        decision.rule = "Scelta del decisore confermata dalle regole.";
        trace.decided(decision, "Jev (jev-1.14.0)");
        assertTrue(output(), output().contains("Deciso da : Jev (jev-1.14.0)"));

        bytes.reset();
        decision.decidedBy = RoutingDecision.DecidedBy.RULES;
        trace.decided(decision, "Jev (jev-1.14.0)");
        assertTrue(output(), output().contains("Deciso da : regole deterministiche"));
        assertFalse(output(), output().contains("Jev"));

        bytes.reset();
        decision.decidedBy = RoutingDecision.DecidedBy.USER;
        trace.decided(decision, "Jev (jev-1.14.0)");
        assertTrue(output(), output().contains("Deciso da : utente"));
    }
}
