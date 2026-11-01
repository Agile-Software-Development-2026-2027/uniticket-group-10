package it.unical.uniticket.llm;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import junit.framework.TestCase;

import java.io.IOException;

public class GeminiLlmClientTest extends TestCase {
    private static final String KEY = "chiave-di-prova";

    private final ObjectMapper mapper = new ObjectMapper();
    private final GeminiLlmClient client = new GeminiLlmClient(KEY, "modello");

    public void testMissingKeyIsRejected() {
        try {
            new GeminiLlmClient("  ", "modello");
            fail("Una chiave vuota deve essere rifiutata.");
        } catch (IllegalArgumentException e) {
            assertTrue(e.getMessage().contains("GEMINI_API_KEY"));
        }
    }

    public void testRequestCarriesPromptsAndDeterministicSettings() {
        ObjectNode request = client.buildRequest("sistema", "utente", null);
        assertEquals("sistema", request.path("systemInstruction").path("parts").path(0).path("text").asText());
        assertEquals("user", request.path("contents").path(0).path("role").asText());
        assertEquals("utente", request.path("contents").path(0).path("parts").path(0).path("text").asText());
        assertEquals(0.0, request.path("generationConfig").path("temperature").asDouble());
        assertEquals("application/json", request.path("generationConfig").path("responseMimeType").asText());
        assertTrue(request.path("generationConfig").path("responseJsonSchema").isMissingNode());
    }

    public void testRequestCarriesTheSchemaButNeverTheKey() {
        ObjectNode schema = mapper.createObjectNode().put("type", "object");
        ObjectNode request = client.buildRequest("sistema", "utente", schema);
        assertEquals("object", request.path("generationConfig").path("responseJsonSchema").path("type").asText());
        assertFalse(request.toString().contains(KEY));
    }

    public void testTextPartsAreJoined() throws IOException {
        JsonNode reply = mapper.readTree("{\"candidates\":[{\"content\":{\"parts\":"
                + "[{\"text\":\"{\\\"match\\\":\"},{\"text\":\"1}\"}]}}]}");
        assertEquals("{\"match\":1}", client.extractText(reply));
    }

    public void testReplyWithoutTextNamesTheReason() throws IOException {
        JsonNode reply = mapper.readTree("{\"candidates\":[{\"finishReason\":\"MAX_TOKENS\"}]}");
        try {
            client.extractText(reply);
            fail("Una risposta senza testo deve essere segnalata.");
        } catch (IllegalStateException e) {
            assertTrue(e.getMessage().contains("MAX_TOKENS"));
        }
    }
}
