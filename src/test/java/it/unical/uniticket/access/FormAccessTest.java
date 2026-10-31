package it.unical.uniticket.access;

import com.fasterxml.jackson.databind.ObjectMapper;
import it.unical.uniticket.api.dto.CategoryFormSchema;
import junit.framework.TestCase;

public class FormAccessTest extends TestCase {
    private static final UserProfile STUDENT = UserProfile.of(UserProfile.Role.STUDENT, "dimes");
    private static final UserProfile STAFF = UserProfile.of(UserProfile.Role.STAFF, "dimes");

    private static CategoryFormSchema form(boolean accessible, String reason) {
        CategoryFormSchema form = new CategoryFormSchema();
        form.accessible = accessible;
        form.accessRestrictionReason = reason;
        return form;
    }

    public void testOpenFormIsOpenForEveryone() {
        assertEquals(FormAccess.OPEN, FormAccess.of(form(true, null), STUDENT));
        assertEquals(FormAccess.OPEN, FormAccess.of(form(true, null), UserProfile.unknown()));
    }

    public void testRoleDeniedFormIsHiddenFromStudentsAndOpenForStaff() {
        CategoryFormSchema staffOnly = form(false, "HTTP 403: Permesso negato a questa tipologia di utente");
        assertEquals(FormAccess.HIDDEN, FormAccess.of(staffOnly, STUDENT));
        assertEquals(FormAccess.HIDDEN, FormAccess.of(staffOnly, UserProfile.unknown()));
        assertEquals(FormAccess.OPEN, FormAccess.of(staffOnly, STAFF));
    }

    public void testNotFoundFormIsClosedForEveryone() {
        CategoryFormSchema closed = form(false, "HTTP 404: Modulo aperto dal primo luglio al 31 agosto");
        assertEquals(FormAccess.CLOSED, FormAccess.of(closed, STUDENT));
        assertEquals(FormAccess.CLOSED, FormAccess.of(closed, STAFF));
    }

    private static CategoryFormSchema closed(String title, String reason) {
        CategoryFormSchema form = form(false, reason);
        form.categoryTitle = title;
        form.availability = new ObjectMapper().createObjectNode().put("observedAt", "2026-10-29T06:19:17Z");
        return form;
    }

    public void testArchivedTitlesAreRetired() {
        assertEquals(FormAccess.RETIRED, FormAccess.of(
                closed("X - Domanda borsa", "HTTP 404: La tipologia di richiesta non è attiva"), STUDENT));
        assertEquals(FormAccess.RETIRED, FormAccess.of(
                closed("z-----Richiesta di Abbreviazione", "HTTP 404: Modulo non più utilizzato"), STUDENT));
    }

    public void testFinishedFormsAreRetired() {
        assertEquals(FormAccess.RETIRED, FormAccess.of(
                closed("Esami a distanza", "HTTP 404: dal 08 Gennaio 2023 non è più possibile inviare richieste"), STUDENT));
        assertEquals(FormAccess.RETIRED, FormAccess.of(
                closed("Variazione", "HTTP 404: La richiesta è scaduta il 15/02/2023"), STAFF));
    }

    public void testOldEditionsAreRetiredButRecentOnesAreNot() {
        String inactive = "HTTP 404: La tipologia di richiesta non è attiva";
        assertEquals(FormAccess.RETIRED, FormAccess.of(closed("Contributo a.a. 2024/2025", inactive), STUDENT));
        assertEquals(FormAccess.CLOSED, FormAccess.of(closed("Domanda borsa di studio 2025/2026", inactive), STUDENT));
    }

    public void testSeasonalAndAmbiguousFormsStayClosed() {
        assertEquals(FormAccess.CLOSED, FormAccess.of(
                closed("Trasferimento", "HTTP 404: Modulo aperto dal primo luglio al 31 agosto"), STUDENT));
        assertEquals(FormAccess.CLOSED, FormAccess.of(
                closed("Cambio classe", "HTTP 404: La tipologia di richiesta non è attiva"), STUDENT));
        assertEquals(FormAccess.CLOSED, FormAccess.of(
                closed("Recupero crediti a.a. 2020/2021", "HTTP 404: Modulo attivo dal lunedì ore 9 al venerdì ore 14"), STUDENT));
    }

    public void testRoleDeniedFormsAreNeverRetired() {
        assertEquals(FormAccess.HIDDEN, FormAccess.of(
                closed("X - Personale", "HTTP 403: Permesso negato a questa tipologia di utente"), STUDENT));
    }

    public void testClosureReasonDropsTheHttpPrefix() {
        assertEquals("Modulo aperto dal primo luglio al 31 agosto", FormAccess.closureReason(
                form(false, "HTTP 404: Modulo aperto dal primo luglio al 31 agosto")));
        assertEquals("", FormAccess.closureReason(form(true, null)));
    }
}
