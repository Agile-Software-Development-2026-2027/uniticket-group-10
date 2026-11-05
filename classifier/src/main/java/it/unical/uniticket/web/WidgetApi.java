package it.unical.uniticket.web;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import it.unical.uniticket.Json;
import it.unical.uniticket.catalog.Catalog;
import it.unical.uniticket.catalog.Category;
import it.unical.uniticket.dialog.ChatBot;
import it.unical.uniticket.dialog.ChatSession;
import it.unical.uniticket.dialog.Reply;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.regex.Pattern;

/**
 * Il contratto di {@code POST /conversation}, lo stesso del servizio {@code agent/}: Django inoltra
 * l'input del widget e aggiunge il catalogo che l'utente può aprire e la lingua.
 *
 * <pre>
 * richiesta: {"input": {"type": "message", "message": "...", "category_id": 12, "thread_id": "uuid"},
 *             "catalog": [{"id": 12, "name": "...", "structure_name": "...", "url": "/...", "hidden": false}],
 *             "language": "it"}
 * risposta:  {"messages": [{"id": "uuid", "message": "...",
 *              "content": {"type": "tickets", "tickets": [{"category_id": 12, "title": "...", ...}]},
 *              "suggestions": ["Sì", "No"],
 *              "action": {"type": "request_form_help", "category_id": 12, "label": "..."}}]}
 * </pre>
 *
 * <p>Il tipo dell'input decide il percorso: {@code message} passa dal classificatore,
 * {@code form_selected} (l'utente ha aperto un modulo) propone l'aiuto alla compilazione,
 * {@code request_form_help} lo avvia. Le risposte agli ultimi due sono quelle di {@code agent/}.
 *
 * <p>Il catalogo di Django usa i propri id; i moduli del classificatore si riconoscono dall'URL,
 * che finisce con struttura e slug ({@code /tickets/new/ict/e3-richiesta-assistenza-esse3/}).
 * Solo i moduli presenti nel catalogo di Django, e non nascosti, possono essere proposti.
 */
public final class WidgetApi {

    /** Una risposta HTTP: status e corpo JSON. */
    public record Response(int status, JsonNode body) {
    }

    /** Una voce del catalogo di Django. */
    private record PortalCategory(int id, String name, String structureName, String url, boolean hidden) {
    }

    private static final int MAX_MESSAGE_CHARS = 500;
    private static final Pattern UUID_FORMAT =
            Pattern.compile("[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}");

    private final Catalog catalog;
    private final ChatBot bot;
    private final Sessions sessions;

    public WidgetApi(Catalog catalog, ChatBot bot, Sessions sessions) {
        this.catalog = catalog;
        this.bot = bot;
        this.sessions = sessions;
    }

    public Response handle(JsonNode request) {
        try {
            return route(request);
        } catch (InvalidRequest e) {
            return error(422, e.getMessage());
        }
    }

    private Response route(JsonNode request) {
        JsonNode input = request.path("input");
        if (!request.isObject() || !input.isObject()) {
            throw new InvalidRequest("Serve un oggetto JSON con il campo input");
        }
        WidgetTexts texts = WidgetTexts.of(request.path("language").asText("it"));
        Map<Integer, PortalCategory> portal = portalCatalog(request.path("catalog"));
        String threadId = threadId(input.path("thread_id"));
        String type = input.path("type").asText("");
        return switch (type) {
            case "message" -> message(input, portal, threadId, texts);
            case "form_selected" -> formSelected(input, portal, threadId, texts);
            case "request_form_help" -> formHelp(input, portal, texts);
            default -> throw new InvalidRequest("Tipo di input sconosciuto: " + type);
        };
    }

    // ---------------------------------------------------------------- i tre percorsi

    private Response message(JsonNode input, Map<Integer, PortalCategory> portal, String threadId,
                             WidgetTexts texts) {
        JsonNode value = input.path("message");
        String text = value.isTextual() ? value.asText().strip() : "";
        if (text.isEmpty() || text.length() > MAX_MESSAGE_CHARS) {
            throw new InvalidRequest("Il messaggio deve avere da 1 a " + MAX_MESSAGE_CHARS + " caratteri");
        }
        if (input.has("category_id")) {
            positiveId(input.path("category_id"));
        }
        Map<String, PortalCategory> byFormId = byFormId(portal);
        ChatSession session = sessions.get(threadId);
        Reply reply;
        synchronized (session) {
            reply = bot.reply(session, text, category -> byFormId.containsKey(category.id()));
        }
        ObjectNode message = message(texts.reply(reply, catalog));
        List<PortalCategory> tickets = reply.options().stream()
                .map(category -> byFormId.get(category.id())).filter(c -> c != null).toList();
        if (!tickets.isEmpty()) {
            ObjectNode content = message.putObject("content").put("type", "tickets");
            ArrayNode list = content.putArray("tickets");
            tickets.forEach(ticket -> list.addObject().put("category_id", ticket.id()).put("title", ticket.name())
                    .put("structure_name", ticket.structureName()).put("url", ticket.url()));
        }
        if (reply.kind() == Reply.Kind.CONFIRM_STRUCTURE) {
            texts.confirmSuggestions().forEach(message.putArray("suggestions")::add);
        }
        return ok(message);
    }

    private Response formSelected(JsonNode input, Map<Integer, PortalCategory> portal, String threadId,
                                  WidgetTexts texts) {
        PortalCategory selected = selected(input, portal);
        if (selected == null) {
            return error(404, texts.notFound());
        }
        formIdOf(selected.url()).flatMap(catalog::byId).ifPresent(category -> {
            ChatSession session = sessions.get(threadId);
            synchronized (session) {
                bot.opened(session, category);
            }
        });
        ObjectNode message = message(texts.offerHelp(selected.name()));
        message.putObject("action").put("type", "request_form_help").put("category_id", selected.id())
                .put("label", texts.helpLabel());
        return ok(message);
    }

    private Response formHelp(JsonNode input, Map<Integer, PortalCategory> portal, WidgetTexts texts) {
        return selected(input, portal) == null ? error(404, texts.notFound()) : ok(message(texts.startHelp()));
    }

    private static PortalCategory selected(JsonNode input, Map<Integer, PortalCategory> portal) {
        PortalCategory category = portal.get(positiveId(input.path("category_id")));
        return category == null || category.hidden() ? null : category;
    }

    // ---------------------------------------------------------------- lettura della richiesta

    private static Map<Integer, PortalCategory> portalCatalog(JsonNode array) {
        if (!array.isArray()) {
            throw new InvalidRequest("Il catalogo deve essere una lista");
        }
        Map<Integer, PortalCategory> portal = new LinkedHashMap<>();
        for (JsonNode item : array) {
            int id = positiveId(item.path("id"));
            String name = item.path("name").asText("");
            String url = item.path("url").asText("");
            if (name.isBlank() || !url.startsWith("/") || url.startsWith("//")) {
                throw new InvalidRequest("Categoria " + id + " senza nome o con un URL non relativo");
            }
            portal.put(id, new PortalCategory(id, name, item.path("structure_name").asText(""), url,
                    item.path("hidden").asBoolean(false)));
        }
        return portal;
    }

    /** Le categorie visibili di Django, indicizzate con l'id dei moduli del classificatore. */
    private static Map<String, PortalCategory> byFormId(Map<Integer, PortalCategory> portal) {
        Map<String, PortalCategory> byFormId = new LinkedHashMap<>();
        for (PortalCategory category : portal.values()) {
            if (!category.hidden()) {
                formIdOf(category.url()).ifPresent(id -> byFormId.putIfAbsent(id, category));
            }
        }
        return byFormId;
    }

    /** "/tickets/new/ict/e3-richiesta/" → "ict/e3-richiesta": gli ultimi due pezzi del percorso. */
    static Optional<String> formIdOf(String url) {
        String path = url.split("[?#]", 2)[0];
        String[] parts = Arrays.stream(path.split("/")).filter(p -> !p.isEmpty()).toArray(String[]::new);
        return parts.length < 2 ? Optional.empty()
                : Optional.of(parts[parts.length - 2] + "/" + parts[parts.length - 1]);
    }

    private static int positiveId(JsonNode value) {
        if (!value.isIntegralNumber() || value.asLong() <= 0 || value.asLong() > Integer.MAX_VALUE) {
            throw new InvalidRequest("Serve un id intero positivo, ricevuto: " + value);
        }
        return value.asInt();
    }

    /** Senza thread_id ogni messaggio è una conversazione nuova, come nel servizio agent/. */
    private static String threadId(JsonNode value) {
        if (value.isMissingNode() || value.isNull()) {
            return null;
        }
        if (!value.isTextual() || !UUID_FORMAT.matcher(value.asText()).matches()) {
            throw new InvalidRequest("thread_id deve essere un UUID");
        }
        return value.asText().toLowerCase();
    }

    // ---------------------------------------------------------------- costruzione della risposta

    private static ObjectNode message(String text) {
        return Json.object().put("id", UUID.randomUUID().toString()).put("message", text);
    }

    private static Response ok(ObjectNode message) {
        ObjectNode body = Json.object();
        body.putArray("messages").add(message);
        return new Response(200, body);
    }

    private static Response error(int status, String detail) {
        return new Response(status, Json.object().put("detail", detail));
    }

    private static final class InvalidRequest extends RuntimeException {
        InvalidRequest(String message) {
            super(message);
        }
    }
}
