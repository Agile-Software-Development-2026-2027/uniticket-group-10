package it.unical.uniticket.llm;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import junit.framework.TestCase;

import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Deque;
import java.util.concurrent.atomic.AtomicInteger;

/** Verifica le richieste vere su HTTP, contro un server locale che imita le risposte documentate. */
public class JevClientTest extends TestCase {
    private static final String KEY = "chiave-di-prova";
    private static final String SUCCESS = "{\"model\":\"jev-1.14.0\","
            + "\"answers\":{\"urgente\":{\"type\":\"noul\",\"noul\":0.9}},"
            + "\"usage\":{\"input_tokens\":12,\"output_tokens\":3}}";

    private final ObjectMapper mapper = new ObjectMapper();
    private final Deque<Reply> replies = new ArrayDeque<>();
    private final AtomicInteger calls = new AtomicInteger();
    private HttpServer server;
    private JevClient client;
    private volatile String method;
    private volatile String path;
    private volatile String authorization;
    private volatile String contentType;
    private volatile String requestBody;

    private static final class Reply {
        final int status;
        final String body;

        Reply(int status, String body) {
            this.status = status;
            this.body = body;
        }
    }

    @Override
    protected void setUp() throws IOException {
        server = HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        server.createContext("/", this::answer);
        server.start();
        String endpoint = "http://127.0.0.1:" + server.getAddress().getPort() + "/v1/systemone";
        client = new JevClient(KEY, "jev-prova", endpoint, 1);
    }

    @Override
    protected void tearDown() {
        server.stop(0);
    }

    private void answer(HttpExchange exchange) throws IOException {
        calls.incrementAndGet();
        method = exchange.getRequestMethod();
        path = exchange.getRequestURI().getPath();
        authorization = exchange.getRequestHeaders().getFirst("Authorization");
        contentType = exchange.getRequestHeaders().getFirst("Content-Type");
        requestBody = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
        Reply reply = replies.isEmpty() ? new Reply(500, "script esaurito") : replies.removeFirst();
        byte[] body = reply.body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json");
        exchange.sendResponseHeaders(reply.status, body.length == 0 ? -1 : body.length);
        if (body.length > 0) exchange.getResponseBody().write(body);
        exchange.close();
    }

    private JsonNode ask() {
        ObjectNode state = mapper.createObjectNode().put("request", "qui c'è la città");
        ObjectNode questions = mapper.createObjectNode();
        questions.putObject("urgente").put("type", "noul").put("instructions", "È urgente?");
        return client.ask(state, questions);
    }

    private String failureOf(int status, String body) {
        replies.add(new Reply(status, body));
        try {
            ask();
            fail("La risposta HTTP " + status + " deve essere un errore.");
            return "";
        } catch (RuntimeException e) {
            return e.getMessage();
        }
    }

    public void testMissingKeyIsRejected() {
        for (String key : Arrays.asList(null, "", "  ")) {
            try {
                new JevClient(key, "modello");
                fail("Una chiave vuota deve essere rifiutata.");
            } catch (IllegalArgumentException e) {
                assertTrue(e.getMessage().contains("TYPESAFE_API_KEY"));
            }
        }
    }

    public void testRequestCarriesModelStateAndQuestionsButNeverTheKey() {
        ObjectNode state = mapper.createObjectNode().put("request", "testo");
        ObjectNode questions = mapper.createObjectNode();
        questions.putObject("q").put("type", "noul");
        ObjectNode request = client.buildRequest(state, questions);
        assertEquals("jev-prova", request.path("model").asText());
        assertEquals("testo", request.path("state").path("request").asText());
        assertEquals("noul", request.path("questions").path("q").path("type").asText());
        assertFalse(request.toString().contains(KEY));
    }

    public void testPostsToTheEndpointWithTheBearerKey() throws IOException {
        replies.add(new Reply(200, SUCCESS));
        ask();
        assertEquals("POST", method);
        assertEquals("/v1/systemone", path);
        assertEquals("Bearer " + KEY, authorization);
        assertEquals("application/json", contentType);
        assertEquals("jev-prova", mapper.readTree(requestBody).path("model").asText());
    }

    public void testAccentsSurviveTheTrip() throws IOException {
        replies.add(new Reply(200, SUCCESS));
        ask();
        assertEquals("qui c'è la città", mapper.readTree(requestBody).path("state").path("request").asText());
    }

    public void testAnswersAreReturnedByQuestionName() {
        replies.add(new Reply(200, SUCCESS));
        assertEquals(0.9, ask().path("urgente").path("noul").asDouble());
    }

    public void testTemporaryErrorsAreRetried() {
        replies.add(new Reply(429, "{\"detail\":\"troppe richieste\"}"));
        replies.add(new Reply(529, "{\"detail\":\"sovraccarico\"}"));
        replies.add(new Reply(200, SUCCESS));
        assertEquals(0.9, ask().path("urgente").path("noul").asDouble());
        assertEquals(3, calls.get());
    }

    public void testGivesUpAfterThreeAttempts() {
        replies.add(new Reply(529, "{\"detail\":\"sovraccarico\"}"));
        replies.add(new Reply(529, "{\"detail\":\"sovraccarico\"}"));
        String message = failureOf(529, "{\"detail\":\"sovraccarico\"}");
        assertTrue(message, message.contains("HTTP 529"));
        assertEquals(3, calls.get());
    }

    public void testPermanentErrorsAreNotRetried() {
        for (int status : new int[] {400, 401, 403, 413, 422}) {
            calls.set(0);
            String message = failureOf(status, "{\"detail\":\"no\"}");
            assertTrue(message, message.contains("HTTP " + status));
            assertEquals(1, calls.get());
        }
    }

    /** Il corpo è quello restituito dal servizio vero a una chiamata senza chiave. */
    public void testAuthenticationErrorShowsItsMessage() {
        String message = failureOf(403, "{\"detail\":{\"error_type\":\"authentication_error\","
                + "\"message\":\"Must supply an API key! Check your request and try again.\"}}");
        assertTrue(message, message.contains("Must supply an API key!"));
    }

    public void testTextDetailIsShown() {
        String message = failureOf(400, "{\"detail\":\"max_tokens_exceeded\"}");
        assertTrue(message, message.contains("max_tokens_exceeded"));
    }

    public void testValidationErrorNamesTheFieldButNotTheRejectedInput() {
        String message = failureOf(422, "{\"detail\":[{\"loc\":[\"body\",\"state\"],\"msg\":\"Field required\","
                + "\"type\":\"missing\",\"input\":\"dati personali\"}]}");
        assertTrue(message, message.contains("Field required"));
        assertTrue(message, message.contains("state"));
        assertFalse(message, message.contains("dati personali"));
    }

    public void testUnreadableErrorBodiesDoNotHideTheStatus() {
        assertTrue(failureOf(403, "<html>Forbidden</html>").contains("HTTP 403"));
        assertTrue(failureOf(403, "").contains("HTTP 403"));
        assertTrue(failureOf(403, "{}").contains("HTTP 403"));
    }

    public void testKeyNeverAppearsInErrors() {
        assertFalse(failureOf(403, "{\"detail\":\"no\"}").contains(KEY));
    }

    public void testUnreadableSuccessIsAnError() {
        assertTrue(failureOf(200, "<html>").contains("jev-prova"));
    }
}
