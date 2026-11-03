package it.unical.uniticket.catalog;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;

/**
 * Un tipo di richiesta di uniTicket con il suo form.
 *
 * @param id           "struttura/slug", identificativo stabile
 * @param summary      descrizione ripulita; vuota se quella originale non dice nulla
 * @param dateStart    inizio della finestra di apertura (ISO-8601) o null
 * @param dateEnd      fine della finestra di apertura (ISO-8601) o null
 * @param departmental il form è di un dipartimento: vale solo per i suoi afferenti
 * @param notes        avvisi mostrati prima del form; boilerplate = testo legale ripetuto
 * @param fields       campi del form: oggi aiutano a riconoscerlo, domani serviranno a compilarlo
 */
public record Category(
        String id,
        String structure,
        String name,
        String summary,
        Audience audience,
        String dateStart,
        String dateEnd,
        String url,
        boolean departmental,
        List<Note> notes,
        List<Field> fields) {

    public record Audience(boolean students, boolean staff, boolean guests, boolean anonymous) {
    }

    public record Note(String text, boolean boilerplate) {
    }

    public record Field(String id, String label, String type, List<String> options) {
    }

    /** Uno status 200 nello scrape non basta: un form può essere scaduto dopo. */
    public boolean isOpenAt(Instant now) {
        if (dateStart != null && OffsetDateTime.parse(dateStart).toInstant().isAfter(now)) {
            return false;
        }
        return dateEnd == null || OffsetDateTime.parse(dateEnd).toInstant().isAfter(now);
    }

    /** I destinatari in chiaro, per il modello. */
    public String audienceText() {
        List<String> who = new ArrayList<>();
        if (audience.students()) {
            who.add("studenti");
        }
        if (audience.staff()) {
            who.add("personale");
        }
        if (audience.guests()) {
            who.add("esterni");
        }
        if (audience.anonymous()) {
            who.add("chiunque");
        }
        return String.join(", ", who);
    }
}
