package it.unical.uniticket.access;

import com.fasterxml.jackson.databind.JsonNode;
import it.unical.uniticket.api.dto.CategoryFormSchema;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Stato di un modulo per uno specifico utente. È l'unico punto che interpreta la disponibilità.
 *
 * <p>Oggi tutto è dedotto da una scansione con un account studente: un 403 "permesso negato"
 * significa che il modulo è riservato ad altri profili, un 404 che non era attivo in quel
 * momento. Quando arriverà l'esportazione ufficiale, con stato e ruoli reali, basterà
 * sostituire le deduzioni in questa classe.</p>
 */
public enum FormAccess {
    /** L'utente può compilarlo. */
    OPEN,
    /** Esiste ma ora non è compilabile: si cerca solo se nessun modulo aperto corrisponde. */
    CLOSED,
    /** Non tornerà attivo: archiviato, evento concluso o scadenza definitiva. Mai mostrato. */
    RETIRED,
    /** Non riguarda questo profilo: non deve comparire nei risultati. */
    HIDDEN;

    private static final String ROLE_DENIED = "HTTP 403: Permesso negato";
    private static final String NOT_ACTIVE = "HTTP 404";
    private static final String HTTP_PREFIX = "^HTTP \\d{3}:\\s*";
    /** Convenzione degli uffici per i moduli archiviati, ad esempio "X - Domanda ...". */
    private static final Pattern ARCHIVED_TITLE =
            Pattern.compile("^\\s*(x\\s*-|z-+)", Pattern.CASE_INSENSITIVE);
    private static final Pattern FINISHED_REASON = Pattern.compile(
            "non (è )?più|è scaduta il|scaduta alle|è stato attivo fino"
                    + "|form di partecipazione è chiuso|partecipazione all.evento"
                    + "|No OrganizationalStructure",
            Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE);
    private static final Pattern GENERIC_INACTIVE =
            Pattern.compile("non .{0,12}attiv", Pattern.CASE_INSENSITIVE);
    private static final Pattern ACADEMIC_YEAR =
            Pattern.compile("(20\\d\\d)\\s*[/-]\\s*(?:20\\d\\d|\\d\\d)\\b");
    /** Un'edizione annuale è superata se è di almeno due anni prima della scansione. */
    private static final int SUPERSEDED_AFTER_YEARS = 2;

    public static FormAccess of(CategoryFormSchema form, UserProfile profile) {
        if (form.accessible) return OPEN;
        if (isRoleRestricted(form)) return profile.isStaff() ? OPEN : HIDDEN;
        return isRetired(form) ? RETIRED : CLOSED;
    }

    /**
     * Riconosce solo i casi evidenti. Le chiusure generiche e quelle stagionali restano
     * {@link #CLOSED}: "aperto dal 1 luglio al 31 agosto" è un'informazione utile.
     */
    public static boolean isRetired(CategoryFormSchema form) {
        String reason = form.accessRestrictionReason;
        if (form.accessible || reason == null || !reason.startsWith(NOT_ACTIVE)) return false;
        String title = form.categoryTitle == null ? "" : form.categoryTitle;
        if (ARCHIVED_TITLE.matcher(title).find()) return true;
        if (FINISHED_REASON.matcher(reason).find()) return true;
        return GENERIC_INACTIVE.matcher(reason).find() && isSupersededEdition(title, form.availability);
    }

    private static boolean isSupersededEdition(String title, JsonNode availability) {
        Matcher year = ACADEMIC_YEAR.matcher(title);
        if (!year.find() || availability == null) return false;
        String observedAt = availability.path("observedAt").asText("");
        if (observedAt.length() < 4 || !observedAt.substring(0, 4).matches("\\d{4}")) return false;
        return Integer.parseInt(year.group(1))
                <= Integer.parseInt(observedAt.substring(0, 4)) - SUPERSEDED_AFTER_YEARS;
    }

    /** Modulo negato al profilo della scansione perché riservato ad altri ruoli. */
    public static boolean isRoleRestricted(CategoryFormSchema form) {
        return !form.accessible && form.accessRestrictionReason != null
                && form.accessRestrictionReason.startsWith(ROLE_DENIED);
    }

    /** Motivo della chiusura leggibile dall'utente, ad esempio le date di apertura. */
    public static String closureReason(CategoryFormSchema form) {
        if (form.accessRestrictionReason == null) return "";
        return form.accessRestrictionReason.replaceFirst(HTTP_PREFIX, "").trim();
    }
}
