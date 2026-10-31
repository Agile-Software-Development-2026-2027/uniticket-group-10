package it.unical.uniticket.access;

import java.util.Locale;

/**
 * Identità dell'utente ottenuta dal login.
 *
 * <p>Il dipartimento è solo un indizio: un utente può aprire una richiesta per una
 * struttura diversa dalla propria, quindi non viene mai usato per filtrare il catalogo.
 * Il ruolo invece decide quali moduli esistono per quell'utente.</p>
 */
public final class UserProfile {
    public enum Role { STUDENT, STAFF, UNKNOWN }

    private static final UserProfile UNKNOWN = new UserProfile(Role.UNKNOWN, null);

    public final Role role;
    public final String departmentSlug;

    private UserProfile(Role role, String departmentSlug) {
        this.role = role;
        this.departmentSlug = departmentSlug == null || departmentSlug.trim().isEmpty()
                ? null : departmentSlug.trim().toLowerCase(Locale.ROOT);
    }

    public static UserProfile of(Role role, String departmentSlug) {
        return new UserProfile(role, departmentSlug);
    }

    public static UserProfile unknown() {
        return UNKNOWN;
    }

    public boolean isStaff() {
        return role == Role.STAFF;
    }

    public boolean hasDepartment() {
        return departmentSlug != null;
    }

    public boolean belongsTo(String structureSlug) {
        return departmentSlug != null && departmentSlug.equalsIgnoreCase(structureSlug);
    }
}
