package it.unical.uniticket.routing;

import it.unical.uniticket.api.dto.CategoryFormSchema;

import java.text.Normalizer;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Pattern;

/**
 * Riconosce quando il testo nomina una struttura, confrontando parole intere.
 * Serve solo a scegliere tra varianti della stessa pratica, quindi una parola come
 * "fisica" non può far selezionare un modulo: al più orienta tra varianti già individuate.
 */
final class DepartmentMatcher {
    /** Nomi per esteso dei dipartimenti, assenti dal catalogo che riporta solo le sigle. */
    private static final Map<String, List<String>> FULL_NAMES = new HashMap<>();
    static {
        FULL_NAMES.put("demacs", Arrays.asList("matematica e informatica"));
        FULL_NAMES.put("dimes", Arrays.asList("ingegneria informatica"));
        FULL_NAMES.put("dimeg", Arrays.asList("ingegneria meccanica", "ingegneria gestionale"));
        FULL_NAMES.put("diam", Arrays.asList("ingegneria dell ambiente", "ingegneria per l ambiente"));
        FULL_NAMES.put("dinci", Arrays.asList("ingegneria civile"));
        FULL_NAMES.put("ctc", Arrays.asList("dictc", "chimica e tecnologie chimiche"));
        FULL_NAMES.put("dibest", Arrays.asList("biologia ecologia e scienze della terra"));
        FULL_NAMES.put("dfssn", Arrays.asList("farmacia"));
        FULL_NAMES.put("desf", Arrays.asList("economia statistica e finanza"));
        FULL_NAMES.put("discag", Arrays.asList("scienze aziendali e giuridiche"));
        FULL_NAMES.put("dispes", Arrays.asList("scienze politiche e sociali"));
        FULL_NAMES.put("disu", Arrays.asList("studi umanistici"));
        FULL_NAMES.put("dices", Arrays.asList("culture educazione e societa"));
    }

    private DepartmentMatcher() {
    }

    /** Varianti la cui struttura è nominata nel testo, nell'ordine ricevuto. */
    static List<CategoryFormSchema> named(String text, List<CategoryFormSchema> variants) {
        String normalized = " " + normalize(text) + " ";
        List<CategoryFormSchema> result = new ArrayList<>();
        for (CategoryFormSchema variant : variants) {
            if (names(variant).stream().anyMatch(name -> containsPhrase(normalized, name))) {
                result.add(variant);
            }
        }
        return result;
    }

    private static List<String> names(CategoryFormSchema variant) {
        List<String> names = new ArrayList<>();
        names.add(normalize(variant.structureName));
        names.add(normalize(variant.structureSlug == null ? "" : variant.structureSlug.replace('-', ' ')));
        names.addAll(FULL_NAMES.getOrDefault(variant.structureSlug, Collections.emptyList()));
        return names;
    }

    private static boolean containsPhrase(String normalizedText, String name) {
        return !name.isEmpty() && Pattern.compile(" " + Pattern.quote(name) + " ")
                .matcher(normalizedText).find();
    }

    private static String normalize(String text) {
        if (text == null) return "";
        return Normalizer.normalize(text.toLowerCase(Locale.ITALIAN), Normalizer.Form.NFD)
                .replaceAll("\\p{InCombiningDiacriticalMarks}+", "")
                .replaceAll("[^a-z0-9]+", " ")
                .trim();
    }
}
