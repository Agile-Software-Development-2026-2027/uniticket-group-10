package it.unical.uniticket.web;

import com.fasterxml.jackson.databind.JsonNode;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import it.unical.uniticket.Json;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Il server HTTP del JDK, con i due endpoint che Django e docker-compose si aspettano dal servizio
 * dell'assistente: {@code GET /health} e {@code POST /conversation}.
 */
public final class WebServer {

    /** Il catalogo di Django sta in qualche centinaio di KB: oltre questo limite non è una richiesta valida. */
    private static final int MAX_BODY_BYTES = 4 * 1024 * 1024;
    private static final int THREADS = 8;

    private final HttpServer server;

    public WebServer(WidgetApi api, String host, int port) throws IOException {
        server = HttpServer.create(new InetSocketAddress(host, port), 0);
        server.setExecutor(Executors.newFixedThreadPool(THREADS));
        server.createContext("/health", exchange -> {
            if (!exactly(exchange, "/health", "GET")) {
                return;
            }
            send(exchange, 200, Json.object().put("status", "ok"));
        });
        server.createContext("/conversation", exchange -> {
            if (!exactly(exchange, "/conversation", "POST")) {
                return;
            }
            JsonNode request = read(exchange);
            if (request == null) {
                send(exchange, 422, Json.object().put("detail", "Serve un corpo JSON di al massimo 4 MB"));
                return;
            }
            WidgetApi.Response response;
            try {
                response = api.handle(request);
            } catch (RuntimeException e) {
                System.err.println("Errore nella conversazione: " + e);
                response = new WidgetApi.Response(503, Json.object().put("detail", "Agent execution failed"));
            }
            send(exchange, response.status(), response.body());
        });
    }

    public void start() {
        server.start();
    }

    public void stop() {
        server.stop(0);
        ((ExecutorService) server.getExecutor()).shutdownNow();
    }

    /** La porta vera, utile quando si chiede la porta 0 (nei test). */
    public int port() {
        return server.getAddress().getPort();
    }

    /** Il contesto risponde anche ai sottopercorsi: qui si accetta solo il percorso esatto. */
    private static boolean exactly(HttpExchange exchange, String path, String method) throws IOException {
        if (!exchange.getRequestURI().getPath().equals(path)) {
            send(exchange, 404, Json.object().put("detail", "Not Found"));
            return false;
        }
        if (!exchange.getRequestMethod().equals(method)) {
            exchange.getResponseHeaders().set("Allow", method);
            send(exchange, 405, Json.object().put("detail", "Method Not Allowed"));
            return false;
        }
        return true;
    }

    private static JsonNode read(HttpExchange exchange) throws IOException {
        try (InputStream in = exchange.getRequestBody()) {
            byte[] body = in.readNBytes(MAX_BODY_BYTES + 1);
            if (body.length > MAX_BODY_BYTES) {
                return null;
            }
            return Json.parse(new String(body, StandardCharsets.UTF_8));
        } catch (IllegalArgumentException e) {
            return null;
        }
    }

    private static void send(HttpExchange exchange, int status, JsonNode body) throws IOException {
        byte[] bytes = Json.write(body).getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json");
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }
}
