package it.unical.uniticket.routing;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import it.unical.uniticket.access.UserProfile;
import it.unical.uniticket.llm.EmbeddingClient;
import it.unical.uniticket.rag.UniTicketRagEngine;
import it.unical.uniticket.rag.UniTicketRagEngine.ScoredCategory;
import junit.framework.TestCase;

import java.io.File;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.stream.Collectors;

public class FormRouterTest extends TestCase {
    private static final String INACTIVE = "HTTP 404: La tipologia di richiesta non è attiva";
    private static final UserProfile STUDENT = UserProfile.of(UserProfile.Role.STUDENT, "desf");
    private static final String QUERY = "richiesta tesi";

    /**
     * Query e documenti coincidono, quindi la similarità di ricerca è piena; i titoli sono
     * ortogonali, tranne quelli uguali, così i raggruppamenti restano quelli attesi.
     */
    private static final EmbeddingClient EMBEDDINGS = new EmbeddingClient() {
        private static final int DIMENSIONS = 32;

        @Override
        public float[] embed(String text) {
            boolean searchText = text.contains("|") || text.equals(QUERY);
            float[] vector = new float[DIMENSIONS];
            vector[searchText ? 0 : 1 + Math.floorMod(text.hashCode(), DIMENSIONS - 1)] = 1f;
            return vector;
        }

        @Override
        public List<float[]> embedBatch(List<String> texts) {
            return texts.stream().map(this::embed).collect(Collectors.toList());
        }
    };

    /** Sceglie il candidato con lo slug indicato e registra ciò che ha visto. */
    private static final class ScriptedDecider implements FormDecider {
        private final String wanted;
        private final List<List<String>> seen = new ArrayList<>();

        private ScriptedDecider(String wanted) {
            this.wanted = wanted;
        }

        @Override
        public DeciderVerdict decide(String request, List<ScoredCategory> candidates, UserProfile profile) {
            List<String> slugs = candidates.stream()
                    .map(candidate -> candidate.schema.compositeSlug)
                    .collect(Collectors.toList());
            seen.add(slugs);
            return slugs.contains(wanted)
                    ? DeciderVerdict.match(slugs.indexOf(wanted), Collections.emptyList(), null, "", "")
                    : DeciderVerdict.noMatch("nessuno");
        }
    }

    private File catalog;

    private static void addForm(ArrayNode forms, String structure, String slug, String title, String reason) {
        ObjectNode form = forms.addObject();
        form.put("compositeSlug", structure + "__" + slug);
        form.put("structureSlug", structure);
        form.put("structureName", structure);
        form.put("categoryTitle", title);
        form.put("ragSearchText", QUERY);
        form.put("accessible", reason == null);
        if (reason != null) form.put("accessRestrictionReason", reason);
    }

    @Override
    protected void setUp() throws Exception {
        ObjectMapper mapper = new ObjectMapper();
        ObjectNode root = mapper.createObjectNode();
        root.putArray("structures");
        ArrayNode forms = root.putArray("allTicketsFlat");
        addForm(forms, "ict", "aperto", "Tesi tesi tesi", null);
        addForm(forms, "ict", "chiuso", "Cambio gruppo filtro", INACTIVE);
        addForm(forms, "ict", "archiviato", "X - Cambio gruppo vecchio", INACTIVE);
        addForm(forms, "dibest", "tesi", "Assegnazione tesi", null);
        addForm(forms, "desf", "tesi", "Assegnazione tesi", INACTIVE);
        catalog = File.createTempFile("catalog", ".json");
        catalog.deleteOnExit();
        mapper.writeValue(catalog, root);
    }

    private RoutingDecision route(FormDecider decider, UserProfile profile) throws Exception {
        UniTicketRagEngine engine = new UniTicketRagEngine(catalog, EMBEDDINGS, null, null);
        return new FormRouter(engine, decider, 8).route(new ConversationState(profile, QUERY));
    }

    public void testReliableOpenFormNeverReachesClosedForms() throws Exception {
        ScriptedDecider decider = new ScriptedDecider("ict__aperto");
        RoutingDecision decision = route(decider, STUDENT);
        assertEquals("ict__aperto", decision.selectedCompositeSlug);
        assertFalse(decision.searchedClosedForms);
        assertEquals(1, decider.seen.size());
        assertFalse(decider.seen.get(0).contains("ict__chiuso"));
    }

    public void testClosedFormIsFoundWhenNoOpenFormMatches() throws Exception {
        ScriptedDecider decider = new ScriptedDecider("ict__chiuso");
        RoutingDecision decision = route(decider, STUDENT);
        assertEquals("ict__chiuso", decision.selectedCompositeSlug);
        assertTrue(decision.isClosedForm());
        assertTrue(decision.searchedClosedForms);
        assertEquals(2, decider.seen.size());
    }

    public void testRetiredFormIsNeverAConsideredCandidate() throws Exception {
        ScriptedDecider decider = new ScriptedDecider("ict__archiviato");
        RoutingDecision decision = route(decider, STUDENT);
        decider.seen.forEach(slugs -> assertFalse(slugs.contains("ict__archiviato")));
        assertTrue(decision.clarifyOptions.stream()
                .noneMatch(option -> option.schema.compositeSlug.equals("ict__archiviato")));
    }

    public void testOwnClosedVariantWinsEvenWhenSearchingOpenForms() throws Exception {
        ScriptedDecider decider = new ScriptedDecider("dibest__tesi");
        RoutingDecision decision = route(decider, STUDENT);
        assertEquals("desf__tesi", decision.selectedCompositeSlug);
        assertTrue(decision.isClosedForm());
        assertFalse(decision.searchedClosedForms);
    }
}
