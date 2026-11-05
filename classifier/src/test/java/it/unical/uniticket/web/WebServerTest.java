package it.unical.uniticket.web;

import static it.unical.uniticket.TestData.CATALOG;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;

import it.unical.uniticket.Http;
import it.unical.uniticket.Json;
import it.unical.uniticket.catalog.Category;
import it.unical.uniticket.dialog.ChatBot;
import it.unical.uniticket.dialog.ChatSession;
import it.unical.uniticket.dialog.DecisionPolicy;
import it.unical.uniticket.estimate.Estimate;
import it.unical.uniticket.estimate.Estimator;
import it.unical.uniticket.estimate.Turn;
import it.unical.uniticket.search.LexicalSearch;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/** Il server vero su una porta libera, con un modello che non risponde mai: nessuna chiamata esterna. */
class WebServerTest {

    private static final HttpClient CLIENT = HttpClient.newHttpClient();
    private WebServer server;

    @BeforeEach
    void start() throws Exception {
        Estimator offline = new Estimator() {
            @Override
            public Estimate estimate(List<Turn> conversation, List<Category> candidates) {
                throw new Http.ServiceException("nessun modello nei test");
            }

            @Override
            public String name() {
                return "offline";
            }
        };
        Clock clock = Clock.fixed(CATALOG.fetchedAt(), ZoneOffset.UTC);
        ChatBot bot = new ChatBot(CATALOG, new LexicalSearch(CATALOG), offline,
                new DecisionPolicy(DecisionPolicy.Params.DEFAULT), clock);
        server = new WebServer(new WidgetApi(CATALOG, bot, new Sessions(Duration.ofMinutes(30), 100, clock)),
                "127.0.0.1", 0);
        server.start();
    }

    @AfterEach
    void stop() {
        server.stop();
    }

    private HttpResponse<String> send(String method, String path, String body) throws Exception {
        HttpRequest.Builder request = HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + server.port() + path))
                .header("Content-Type", "application/json");
        request.method(method, body == null ? HttpRequest.BodyPublishers.noBody() : HttpRequest.BodyPublishers.ofString(body));
        return CLIENT.send(request.build(), HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void healthRispondeOkComeSiAspettaIlHealthcheck() throws Exception {
        HttpResponse<String> response = send("GET", "/health", null);
        assertEquals(200, response.statusCode());
        assertEquals("ok", Json.parse(response.body()).path("status").asText());
        assertEquals("application/json", response.headers().firstValue("Content-Type").orElse(""));
    }

    @Test
    void conversationRispondeConIMessaggi() throws Exception {
        String body = """
                {"input": {"type": "message", "message": "mi serve un certificato di laurea"},
                 "catalog": [{"id": 7, "name": "Certificato di laurea", "description": "", "structure_name": "DiBEST",
                              "url": "/tickets/new/dibest/richiesta-certificato-di-laurea/", "hidden": false}],
                 "language": "it"}""";
        HttpResponse<String> response = send("POST", "/conversation", body);
        assertEquals(200, response.statusCode(), response.body());
        assertEquals(7, Json.parse(response.body()).path("messages").get(0).path("content").path("tickets").get(0)
                .path("category_id").asInt());
    }

    @Test
    void metodiPercorsiECorpiSbagliatiNonPassano() throws Exception {
        assertEquals(405, send("GET", "/conversation", null).statusCode());
        assertEquals(404, send("GET", "/health/altro", null).statusCode());
        assertEquals(422, send("POST", "/conversation", "non è json").statusCode());
        assertEquals(422, send("POST", "/conversation", "{}").statusCode());
    }

    @Test
    void leSessioniInattiveSiDimenticano() {
        Instant[] now = {Instant.parse("2026-11-03T10:00:00Z")};
        Clock clock = new Clock() {
            @Override
            public ZoneOffset getZone() {
                return ZoneOffset.UTC;
            }

            @Override
            public Clock withZone(java.time.ZoneId zone) {
                return this;
            }

            @Override
            public Instant instant() {
                return now[0];
            }
        };
        Sessions sessions = new Sessions(Duration.ofMinutes(30), 2, clock);
        ChatSession first = sessions.get("a");
        assertSame(first, sessions.get("a"));
        now[0] = now[0].plus(Duration.ofMinutes(31));
        sessions.get("b");
        assertEquals(1, sessions.size(), "la sessione a è scaduta");
        sessions.get("c");
        sessions.get("d");
        assertEquals(2, sessions.size(), "non più di due sessioni");
    }
}
