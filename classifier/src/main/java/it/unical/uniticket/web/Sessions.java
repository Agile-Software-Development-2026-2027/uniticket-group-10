package it.unical.uniticket.web;

import it.unical.uniticket.dialog.ChatSession;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Comparator;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Una {@link ChatSession} per ogni conversazione del widget, riconosciuta dal suo {@code thread_id}
 * ("Nuova chat" ne genera un altro). Le sessioni stanno in memoria: dopo un riavvio si riparte da capo,
 * che per una ricerca di pochi turni basta.
 */
public final class Sessions {

    private record Entry(ChatSession session, Instant lastUsed) {
    }

    private final Map<String, Entry> entries = new ConcurrentHashMap<>();
    private final Duration idle;
    private final int maxSessions;
    private final Clock clock;

    /**
     * @param idle        dopo quanto tempo senza messaggi una sessione si dimentica
     * @param maxSessions oltre questo numero si dimentica la sessione usata meno di recente
     */
    public Sessions(Duration idle, int maxSessions, Clock clock) {
        this.idle = idle;
        this.maxSessions = maxSessions;
        this.clock = clock;
    }

    /** La sessione di questa conversazione, nuova se non c'è; senza id una sessione usa e getta. */
    public ChatSession get(String threadId) {
        if (threadId == null) {
            return new ChatSession();
        }
        Instant now = clock.instant();
        entries.values().removeIf(entry -> entry.lastUsed().plus(idle).isBefore(now));
        Entry entry = entries.compute(threadId, (id, old) ->
                new Entry(old == null ? new ChatSession() : old.session(), now));
        while (entries.size() > maxSessions) {
            entries.entrySet().stream()
                    .filter(e -> !e.getKey().equals(threadId))
                    .min(Comparator.comparing(e -> e.getValue().lastUsed()))
                    .ifPresent(oldest -> entries.remove(oldest.getKey()));
        }
        return entry.session();
    }

    int size() {
        return entries.size();
    }
}
