package it.unical.uniticket.estimate;

import java.util.List;

/** Una battuta della conversazione. */
public record Turn(boolean fromUser, String text) {

    public static Turn user(String text) {
        return new Turn(true, text);
    }

    public static Turn bot(String text) {
        return new Turn(false, text);
    }

    /** La conversazione come la legge il modello. */
    public static String transcript(List<Turn> turns) {
        StringBuilder text = new StringBuilder();
        for (Turn turn : turns) {
            text.append(turn.fromUser() ? "Utente: " : "Assistente: ").append(turn.text()).append('\n');
        }
        return text.toString();
    }
}
