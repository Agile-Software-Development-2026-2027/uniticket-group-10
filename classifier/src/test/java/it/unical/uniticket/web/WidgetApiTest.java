package it.unical.uniticket.web;

import static it.unical.uniticket.TestData.CATALOG;
import static it.unical.uniticket.TestData.estimate;
import static it.unical.uniticket.TestData.form;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import it.unical.uniticket.Http;
import it.unical.uniticket.Json;
import it.unical.uniticket.catalog.Category;
import it.unical.uniticket.dialog.ChatBot;
import it.unical.uniticket.dialog.DecisionPolicy;
import it.unical.uniticket.estimate.Estimate;
import it.unical.uniticket.estimate.Estimator;
import it.unical.uniticket.estimate.Turn;
import it.unical.uniticket.search.LexicalSearch;
import java.time.Clock;
import java.time.Duration;
import java.time.ZoneOffset;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import java.util.stream.StreamSupport;
import org.junit.jupiter.api.Test;

/** Il contratto con il widget, con un modello finto e un catalogo di Django costruito nei test. */
class WidgetApiTest {

    private static final String ESSE3 = "ict/e3-richiesta-assistenza-esse3";
    private static final String DIBEST = "dibest/richiesta-certificato-di-laurea";
    private static final String DIMES = "dimes/richiesta-certificato-di-iscrizionelaureadiploma-supplement";
    private static final Estimate TIED = estimate(null, 0, 0, DIBEST, 0.5, DIMES, 0.5);
    private static final Clock SCRAPE_DAY = Clock.fixed(CATALOG.fetchedAt(), ZoneOffset.UTC);

    /** Restituisce le stime in ordine; null simula un modello che non risponde. */
    private static final class FakeEstimator implements Estimator {
        private final Deque<Optional<Estimate>> answers = new ArrayDeque<>();
        final List<List<Turn>> conversations = new ArrayList<>();
        List<Category> lastCandidates;

        FakeEstimator then(Estimate estimate) {
            answers.add(Optional.ofNullable(estimate));
            return this;
        }

        @Override
        public Estimate estimate(List<Turn> conversation, List<Category> candidates) {
            conversations.add(List.copyOf(conversation));
            lastCandidates = candidates;
            return answers.poll().orElseThrow(() -> new Http.ServiceException("modello spento"));
        }

        @Override
        public String name() {
            return "finto";
        }
    }

    private final Sessions sessions = new Sessions(Duration.ofMinutes(30), 100, SCRAPE_DAY);

    private WidgetApi api(Estimator estimator) {
        ChatBot bot = new ChatBot(CATALOG, new LexicalSearch(CATALOG), estimator,
                new DecisionPolicy(DecisionPolicy.Params.DEFAULT), SCRAPE_DAY);
        return new WidgetApi(CATALOG, bot, sessions);
    }

    // ---------------------------------------------------------------- richieste come quelle di Django

    /** Il catalogo che Django manderebbe: id propri, URL del modulo, i moduli indicati visibili. */
    private static ArrayNode portal(String... formIds) {
        ArrayNode catalog = Json.MAPPER.createArrayNode();
        for (int i = 0; i < formIds.length; i++) {
            Category category = form(formIds[i]);
            catalog.addObject().put("id", 100 + i).put("name", category.name()).put("description", "")
                    .put("structure_name", category.structure().toUpperCase()).put("hidden", false)
                    .put("url", "/tickets/new/" + category.id() + "/");
        }
        return catalog;
    }

    private static ObjectNode request(ObjectNode input, ArrayNode catalog) {
        ObjectNode request = Json.object();
        request.set("input", input);
        request.set("catalog", catalog);
        return request.put("language", "it");
    }

    private static ObjectNode message(String text, String threadId) {
        ObjectNode input = Json.object().put("type", "message").put("message", text);
        return threadId == null ? input : input.put("thread_id", threadId);
    }

    private static ObjectNode formEvent(String type, int categoryId, String threadId) {
        return Json.object().put("type", type).put("category_id", categoryId).put("thread_id", threadId);
    }

    /** I controlli di assistantMessage() nel widget: se uno fallisce, il widget scarta la risposta. */
    private static JsonNode onlyMessage(WidgetApi.Response response) {
        assertEquals(200, response.status(), response.body().toString());
        JsonNode messages = response.body().path("messages");
        assertEquals(1, messages.size(), response.body().toString());
        JsonNode message = messages.get(0);
        assertTrue(message.path("id").isTextual());
        UUID.fromString(message.path("id").asText());
        assertTrue(message.path("message").isTextual() && !message.path("message").asText().isBlank());
        if (message.has("content")) {
            assertEquals("tickets", message.path("content").path("type").asText());
            for (JsonNode ticket : message.path("content").path("tickets")) {
                assertTrue(ticket.path("title").isTextual());
                assertTrue(ticket.path("category_id").isIntegralNumber());
                String url = ticket.path("url").asText();
                assertTrue(url.startsWith("/") && !url.startsWith("//"), url);
            }
        }
        if (message.has("action")) {
            assertEquals("request_form_help", message.path("action").path("type").asText());
            assertTrue(message.path("action").path("category_id").asInt() > 0);
            assertFalse(message.path("action").path("label").asText().isBlank());
        }
        return message;
    }

    private static List<Integer> ticketIds(JsonNode message) {
        return StreamSupport.stream(message.path("content").path("tickets").spliterator(), false)
                .map(ticket -> ticket.path("category_id").asInt()).toList();
    }

    // ---------------------------------------------------------------- messaggi

    @Test
    void unaRichiestaChiaraDiventaUnaCardConIdEUrlDiDjango() {
        JsonNode message = onlyMessage(api(new FakeEstimator().then(estimate(null, 0, 0, ESSE3, 1.0)))
                .handle(request(message("non riesco ad accedere a Esse3", null), portal(ESSE3, DIBEST))));
        JsonNode ticket = message.path("content").path("tickets").get(0);
        assertEquals(100, ticket.path("category_id").asInt());
        assertEquals("/tickets/new/" + ESSE3 + "/", ticket.path("url").asText());
        assertEquals(form(ESSE3).name(), ticket.path("title").asText());
        assertEquals("ICT", ticket.path("structure_name").asText());
    }

    @Test
    void neiDubbiFaLaDomandaEMostraLeOpzioniComeCard() {
        JsonNode message = onlyMessage(api(new FakeEstimator().then(TIED))
                .handle(request(message("mi serve un certificato di laurea", null), portal(DIBEST, DIMES))));
        assertTrue(message.path("message").asText().startsWith("A quale corso di studi o dipartimento"),
                message.toString());
        assertEquals(List.of(100, 101), ticketIds(message));
    }

    @Test
    void ilModelloVedeSoloIModuliDelCatalogoDellUtente() {
        FakeEstimator estimator = new FakeEstimator().then(estimate(null, 0, 1));
        api(estimator).handle(request(message("mi serve un certificato di laurea", null), portal(DIMES)));
        assertEquals(List.of(form(DIMES)), estimator.lastCandidates);
    }

    @Test
    void iModuliNascostiNonVengonoProposti() {
        ArrayNode catalog = portal(DIBEST, DIMES);
        ((ObjectNode) catalog.get(0)).put("hidden", true);
        FakeEstimator estimator = new FakeEstimator().then(estimate(null, 0, 1));
        api(estimator).handle(request(message("mi serve un certificato di laurea", null), catalog));
        assertFalse(estimator.lastCandidates.contains(form(DIBEST)));
    }

    @Test
    void conIlThreadIdLaConversazioneContinua() {
        String thread = UUID.randomUUID().toString();
        FakeEstimator estimator = new FakeEstimator().then(TIED).then(estimate("dimes", 0, 0, DIMES, 1.0));
        WidgetApi api = api(estimator);
        api.handle(request(message("mi serve un certificato di laurea", thread), portal(DIBEST, DIMES)));

        JsonNode second = onlyMessage(api.handle(
                request(message("sono di ingegneria informatica", thread), portal(DIBEST, DIMES))));

        assertEquals(List.of(101), ticketIds(second));
        String transcript = Turn.transcript(estimator.conversations.get(1));
        assertTrue(transcript.contains("Utente: mi serve un certificato di laurea"), transcript);
        assertTrue(transcript.contains("Utente: sono di ingegneria informatica"), transcript);
    }

    @Test
    void unaRispostaChiusaNelThreadNonChiamaIlModello() {
        String thread = UUID.randomUUID().toString();
        FakeEstimator estimator = new FakeEstimator().then(TIED);
        WidgetApi api = api(estimator);
        api.handle(request(message("mi serve un certificato di laurea", thread), portal(DIBEST, DIMES)));

        JsonNode chosen = onlyMessage(api.handle(request(message("2", thread), portal(DIBEST, DIMES))));

        assertEquals(List.of(101), ticketIds(chosen));
        assertEquals(1, estimator.conversations.size());
    }

    @Test
    void senzaThreadIdOgniMessaggioEUnaConversazioneNuova() {
        FakeEstimator estimator = new FakeEstimator().then(TIED).then(estimate(null, 0, 1));
        WidgetApi api = api(estimator);
        api.handle(request(message("mi serve un certificato di laurea", null), portal(DIBEST, DIMES)));
        api.handle(request(message("sono di ingegneria informatica", null), portal(DIBEST, DIMES)));
        assertEquals(1, estimator.conversations.get(1).size(), "il secondo turno non sa del primo");
    }

    @Test
    void unModuloDiDipartimentoDaConfermareHaISuggerimentiSiENo() {
        String thread = UUID.randomUUID().toString();
        WidgetApi api = api(new FakeEstimator().then(estimate("dimes", 0, 0, DIMES, 1.0)));
        JsonNode message = onlyMessage(api.handle(
                request(message("mi serve un certificato di laurea", thread), portal(DIMES))));
        assertEquals(List.of("Sì", "No"), Json.MAPPER.convertValue(message.path("suggestions"), List.class));

        JsonNode confirmed = onlyMessage(api.handle(request(message("Sì", thread), portal(DIMES))));
        assertEquals(List.of(100), ticketIds(confirmed));
    }

    @Test
    void senzaModuloAdattoNonCiSonoCard() {
        JsonNode message = onlyMessage(api(new FakeEstimator().then(estimate(null, 1.0, 0)))
                .handle(request(message("voglio prenotare un volo", null), portal(ESSE3))));
        assertFalse(message.has("content"));
        assertTrue(message.path("message").asText().startsWith("Non ho trovato richieste adatte"));
    }

    @Test
    void seIlModelloNonRispondeRestanoICandidatiDellaRicerca() {
        JsonNode message = onlyMessage(api(new FakeEstimator().then(null))
                .handle(request(message("mi serve un certificato di laurea", null), portal(DIBEST, DIMES, ESSE3))));
        assertFalse(ticketIds(message).isEmpty());
        assertTrue(message.path("message").asText().startsWith("Al momento non riesco"));
    }

    @Test
    void inIngleseRispondeInInglese() {
        ObjectNode request = request(message("I need a degree certificate", null), portal(DIBEST, DIMES));
        request.put("language", "en");
        JsonNode message = onlyMessage(api(new FakeEstimator().then(TIED)).handle(request));
        assertTrue(message.path("message").asText().startsWith("Which degree course or department"),
                message.toString());
    }

    // ---------------------------------------------------------------- moduli aperti e aiuto alla compilazione

    @Test
    void aprireUnModuloProponeLAiutoEChiudeLaRicerca() {
        String thread = UUID.randomUUID().toString();
        FakeEstimator estimator = new FakeEstimator().then(TIED).then(estimate(null, 0, 1));
        WidgetApi api = api(estimator);
        api.handle(request(message("mi serve un certificato di laurea", thread), portal(DIBEST, DIMES)));

        JsonNode offer = onlyMessage(api.handle(request(formEvent("form_selected", 101, thread), portal(DIBEST, DIMES))));
        assertEquals(101, offer.path("action").path("category_id").asInt());
        assertEquals("Aiutami a compilare questa richiesta", offer.path("action").path("label").asText());
        assertEquals("Vuoi aiuto a compilare la richiesta «" + form(DIMES).name() + "»?",
                offer.path("message").asText());

        api.handle(request(message("ora mi serve altro", thread), portal(DIBEST, DIMES)));
        assertEquals(1, estimator.conversations.get(1).size(), "dopo l'apertura si riparte da capo");
    }

    @Test
    void lAiutoAllaCompilazioneRispondeComeAgent() {
        JsonNode message = onlyMessage(api(new FakeEstimator())
                .handle(request(formEvent("request_form_help", 100, UUID.randomUUID().toString()), portal(ESSE3))));
        assertEquals("Ti aiuto a compilare la richiesta. Da quale campo vuoi partire?", message.path("message").asText());
    }

    @Test
    void unModuloNonNelCatalogoEUn404() {
        WidgetApi.Response response = api(new FakeEstimator())
                .handle(request(formEvent("form_selected", 999, UUID.randomUUID().toString()), portal(ESSE3)));
        assertEquals(404, response.status());
        assertEquals("Domanda non trovata o scaduta.", response.body().path("detail").asText());
    }

    // ---------------------------------------------------------------- richieste non valide

    @Test
    void lerichiesteNonValideSonoUn422() {
        WidgetApi api = api(new FakeEstimator());
        List<ObjectNode> invalid = List.of(
                request(message("   ", null), portal(ESSE3)),
                request(message("x".repeat(501), null), portal(ESSE3)),
                request(Json.object().put("type", "altro"), portal(ESSE3)),
                request(message("ciao", "non-un-uuid"), portal(ESSE3)),
                request(Json.object().put("type", "form_selected").put("category_id", -1), portal(ESSE3)),
                (ObjectNode) Json.object().put("language", "it"));
        for (ObjectNode request : invalid) {
            assertEquals(422, api.handle(request).status(), request.toString());
        }
        ObjectNode notAList = request(message("ciao", null), portal(ESSE3));
        notAList.put("catalog", "tutto");
        assertEquals(422, api.handle(notAList).status());
    }

    @Test
    void lIdDelModuloSiLeggeDallUrl() {
        assertEquals(Optional.of(ESSE3), WidgetApi.formIdOf("/tickets/new/" + ESSE3 + "/"));
        assertEquals(Optional.of(ESSE3), WidgetApi.formIdOf("/it/tickets/new/" + ESSE3 + "?x=1"));
        assertEquals(Optional.empty(), WidgetApi.formIdOf("/"));
    }
}
