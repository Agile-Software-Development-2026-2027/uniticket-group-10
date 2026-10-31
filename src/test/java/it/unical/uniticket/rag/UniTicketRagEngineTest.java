package it.unical.uniticket.rag;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import it.unical.uniticket.access.UserProfile;
import it.unical.uniticket.rag.UniTicketRagEngine.ScoredCategory;
import junit.framework.TestCase;

import java.io.File;
import java.util.Collections;
import java.util.List;

public class UniTicketRagEngineTest extends TestCase {
    private UniTicketRagEngine engine;

    @Override
    protected void setUp() throws Exception {
        ObjectMapper mapper = new ObjectMapper();
        ObjectNode root = mapper.createObjectNode();
        root.putArray("structures");
        ObjectNode form = root.putArray("allTicketsFlat").addObject();
        form.put("compositeSlug", "dimes__piano");
        form.put("structureSlug", "dimes");
        form.put("structureName", "DIMES");
        form.put("categoryTitle", "Piano di studio e ufficio servizio");
        form.put("accessible", true);
        File catalog = File.createTempFile("catalog", ".json");
        catalog.deleteOnExit();
        mapper.writeValue(catalog, root);
        engine = new UniTicketRagEngine(catalog, null, null, null);
    }

    private List<ScoredCategory> search(String query) {
        return engine.search(query, 5, UserProfile.unknown(), Collections.emptySet());
    }

    public void testSingularAndPluralOfIoWordsMatch() {
        assertEquals(1, search("studi").size());
        assertEquals(1, search("uffici").size());
        assertEquals(1, search("servizi").size());
    }

    public void testUnrelatedWordDoesNotMatch() {
        assertEquals(0, search("mensa").size());
    }
}
