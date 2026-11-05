package it.unical.uniticket.dialog;

import java.util.List;
import java.util.Locale;
import java.util.OptionalInt;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Riconosce le risposte chiuse: un numero ("2", "la seconda"), un sì, un no. Sono casi senza
 * ambiguità, quindi non serve il modello. Le espressioni sono ancorate all'intero messaggio:
 * "sono al 2 anno" non è la scelta dell'opzione 2.
 */
final class UserChoice {

    private static final Pattern NUMBER =
            Pattern.compile("^(?:(?:la|il|l'|opzione|numero|modulo|n\\.?)\\s*)*(\\d{1,2})[.)]?$");
    private static final Pattern ORDINAL =
            Pattern.compile("^(?:(?:la|il|l')\\s*)?([a-z]+)(?:\\s+(?:opzione|scelta|voce|modulo))?$");
    private static final List<String> ORDINALS = List.of("prima", "seconda", "terza", "quarta", "quinta");
    private static final List<String> ORDINALS_MALE = List.of("primo", "secondo", "terzo", "quarto", "quinto");
    private static final Pattern ACCEPTANCE = Pattern.compile(
            "^(s[iì]|ok|okay|va bene|perfetto|esatto|giusto|grazie|ok grazie|s[iì] grazie|yes|thanks|thank you)[.!]*$");
    private static final Pattern REJECTION = Pattern.compile(
            "^(no|no grazie|nessun[oa]|nessuna delle due|nessuna di queste|nessuno di questi"
                    + "|non è questo|non e questo|non è quello|altro|altri|none of these|neither)[.!]*$");

    private UserChoice() {
    }

    /** L'indice scelto tra {@code count} opzioni, se il messaggio è soltanto una scelta. */
    static OptionalInt parse(String text, int count) {
        String normalized = normalize(text);
        int index = -1;
        Matcher number = NUMBER.matcher(normalized);
        Matcher ordinal = ORDINAL.matcher(normalized);
        if (number.matches()) {
            index = Integer.parseInt(number.group(1)) - 1;
        } else if (ordinal.matches()) {
            index = Math.max(ORDINALS.indexOf(ordinal.group(1)), ORDINALS_MALE.indexOf(ordinal.group(1)));
        }
        return index >= 0 && index < count ? OptionalInt.of(index) : OptionalInt.empty();
    }

    static boolean isAcceptance(String text) {
        return ACCEPTANCE.matcher(normalize(text)).matches();
    }

    static boolean isRejection(String text) {
        return REJECTION.matcher(normalize(text)).matches();
    }

    private static String normalize(String text) {
        return text.strip().toLowerCase(Locale.ROOT);
    }
}
