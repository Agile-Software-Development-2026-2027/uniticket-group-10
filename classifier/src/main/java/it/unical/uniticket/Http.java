package it.unical.uniticket;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;

/**
 * POST JSON con nuovi tentativi. Ai modelli e agli embedding basta questo: un SDK per servizio
 * aggiungerebbe dipendenze senza togliere complessità.
 */
public final class Http {

    /** Un servizio esterno (modello, embedding) non ha risposto come doveva. */
    public static final class ServiceException extends RuntimeException {
        public ServiceException(String message) {
            super(message);
        }
    }

    private static final HttpClient CLIENT = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(10)).build();
    private static final int MAX_ATTEMPTS = 3;
    /** Un limite al minuto si libera entro un minuto; un'attesa più lunga è una quota giornaliera finita. */
    private static final long MAX_WAIT_MILLIS = 65_000;

    private Http() {
    }

    /**
     * Invia il corpo e restituisce la risposta se lo status è 200. Ripete gli errori temporanei
     * (rete, 408, 429, 5xx) rispettando l'attesa chiesta dal server.
     */
    public static String post(String url, Map<String, String> headers, String body, Duration timeout) {
        URI uri = URI.create(url);
        ServiceException last = null;
        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            HttpRequest.Builder request = HttpRequest.newBuilder(uri).timeout(timeout)
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(body, StandardCharsets.UTF_8));
            headers.forEach(request::header);
            long wait = 1000L << attempt;
            try {
                HttpResponse<String> response = CLIENT.send(request.build(),
                        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
                int status = response.statusCode();
                if (status == 200) {
                    return response.body();
                }
                last = new ServiceException(uri.getHost() + ": HTTP " + status + " " + Json.abbreviate(response.body()));
                if (status != 408 && status != 429 && status < 500) {
                    throw last; // errore della richiesta: riprovare non serve
                }
                wait = retryAfter(response, wait);
            } catch (IOException e) {
                last = new ServiceException(uri.getHost() + " non raggiungibile: " + e.getMessage());
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new ServiceException("Richiesta interrotta");
            }
            if (attempt == MAX_ATTEMPTS || wait > MAX_WAIT_MILLIS) {
                break;
            }
            sleep(wait);
        }
        throw last;
    }

    private static long retryAfter(HttpResponse<String> response, long fallback) {
        try {
            return response.headers().firstValue("retry-after").map(s -> Long.parseLong(s.strip()) * 1000)
                    .orElse(fallback);
        } catch (NumberFormatException e) {
            return fallback;
        }
    }

    private static void sleep(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new ServiceException("Attesa interrotta");
        }
    }
}
