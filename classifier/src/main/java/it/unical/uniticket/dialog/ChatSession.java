package it.unical.uniticket.dialog;

import it.unical.uniticket.catalog.Category;
import it.unical.uniticket.estimate.Turn;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

/**
 * Lo stato di una conversazione: cosa si sono detti utente e bot, quali moduli il bot ha proposto
 * e quali l'utente ha rifiutato, quante domande ha già fatto il bot.
 *
 * <p>È solo un contenitore di dati, senza logica: la logica sta in {@link ChatBot}, che non ha stato.
 * Così un solo {@code ChatBot} serve tutti gli utenti, e un'interfaccia web dovrebbe solo tenere una
 * sessione per utente e salvarla tra una richiesta e l'altra.
 *
 * <p>Si legge da fuori, si modifica solo dal pacchetto {@code dialog}.
 */
public final class ChatSession {

    private final List<Turn> conversation = new ArrayList<>();
    private final Set<String> rejected = new LinkedHashSet<>();
    private List<Category> proposed = List.of();
    private int questionsAsked;
    private boolean closed;

    /** La conversazione finora, messaggi dell'utente e riassunti di cosa ha fatto il bot. */
    public List<Turn> conversation() {
        return List.copyOf(conversation);
    }

    /** Gli id dei moduli rifiutati dall'utente: non tornano più tra i candidati. */
    public Set<String> rejected() {
        return Set.copyOf(rejected);
    }

    /** I moduli proposti nell'ultima risposta del bot. */
    public List<Category> proposed() {
        return proposed;
    }

    public int questionsAsked() {
        return questionsAsked;
    }

    /** Ricomincia da capo per una nuova richiesta. */
    public void reset() {
        conversation.clear();
        rejected.clear();
        proposed = List.of();
        questionsAsked = 0;
        closed = false;
    }

    void addUser(String text) {
        conversation.add(Turn.user(text));
    }

    void addBot(String text) {
        conversation.add(Turn.bot(text));
    }

    void propose(List<Category> options) {
        proposed = List.copyOf(options);
    }

    /** L'utente ha detto "no" o "nessuna di queste": i moduli proposti non vanno più mostrati. */
    void rejectProposed() {
        proposed.forEach(c -> rejected.add(c.id()));
        proposed = List.of();
    }

    void countQuestion() {
        questionsAsked++;
    }

    /** L'utente ha scelto il modulo: il prossimo messaggio è una richiesta nuova. */
    void close() {
        closed = true;
    }

    boolean isClosed() {
        return closed;
    }
}
