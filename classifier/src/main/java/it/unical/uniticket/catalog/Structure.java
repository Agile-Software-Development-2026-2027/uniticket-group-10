package it.unical.uniticket.catalog;

import java.util.List;

/**
 * Una struttura di Ateneo (dipartimento, ufficio, biblioteca).
 *
 * @param name     nome in uniTicket, spesso solo una sigla ("DiBEST")
 * @param fullName nome esteso, da {@code data/structures-extra.json}
 * @param aliases  altri modi in cui gli utenti la chiamano
 * @param courses  corsi di studio: "sono di Giurisprudenza" identifica la struttura
 */
public record Structure(String slug, String name, String fullName, List<String> aliases, List<String> courses) {

    public boolean isDepartment() {
        return fullName != null && fullName.startsWith("Dipartimento");
    }

    /** Il nome esteso con la sigla, se diversi. */
    public String label() {
        if (fullName == null || fullName.isBlank() || fullName.equalsIgnoreCase(name)) {
            return name;
        }
        return fullName + " (" + name + ")";
    }
}
