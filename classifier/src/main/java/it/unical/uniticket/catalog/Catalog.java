package it.unical.uniticket.catalog;

import it.unical.uniticket.Json;
import java.nio.file.Path;
import java.text.Normalizer;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * Il catalogo dei moduli, letto da {@code data/catalog.json} (generato da {@link CatalogBuilder}).
 *
 * <p>Oltre a contenere i dati sa fare due cose che servono in più punti: riconoscere le strutture
 * nominate in un testo e preparare i testi dei moduli per la ricerca e per il modello.
 */
public final class Catalog {

    /**
     * Il contenuto del file.
     *
     * @param fetchedAt  data dello scrape: lo stato dei moduli si riferisce a quel momento
     * @param categories i moduli con il form disponibile (HTTP 200): gli unici candidati
     */
    public record Data(String fetchedAt, List<Structure> structures, List<Category> categories) {
    }

    /** Un'etichetta presente in più form di così ("Cognome", "Matricola") non distingue nulla. */
    private static final int MAX_LABEL_FORMS = 3;
    private static final int MAX_OPTIONS_PER_FIELD = 12;
    private static final Set<String> SYSTEM_FIELDS = Set.of("ticket_subject", "ticket_description",
            "condizioni_field_id");

    private static final Pattern NOT_ALPHANUMERIC = Pattern.compile("[^a-z0-9]+");
    private static final Pattern DIACRITICS = Pattern.compile("\\p{InCombiningDiacriticalMarks}+");
    private static final Pattern PARENTHESIS = Pattern.compile("\\([^)]*\\)");
    /** Dove finisce la prima parte di un corso come "Ingegneria per l'Ambiente e il Territorio". */
    private static final Pattern FIRST_PART_END = Pattern.compile(",|\\s+e\\s+", Pattern.CASE_INSENSITIVE);

    private final Data data;
    private final Map<String, Category> byId = new LinkedHashMap<>();
    private final Map<String, Structure> structures = new LinkedHashMap<>();
    private final Map<String, Set<String>> structurePhrases = new LinkedHashMap<>();
    private final Map<String, Integer> labelForms = new HashMap<>();

    public Catalog(Data data) {
        this.data = data;
        data.categories().forEach(c -> byId.put(c.id(), c));
        data.structures().forEach(s -> {
            structures.put(s.slug(), s);
            structurePhrases.put(s.slug(), phrasesOf(s));
        });
        for (Category category : data.categories()) {
            category.fields().stream().map(f -> f.label().toLowerCase(Locale.ROOT).strip()).distinct()
                    .forEach(label -> labelForms.merge(label, 1, Integer::sum));
        }
    }

    public static Catalog load(Path file) {
        return new Catalog(Json.MAPPER.convertValue(Json.read(file), Data.class));
    }

    public List<Category> categories() {
        return data.categories();
    }

    public List<Structure> structures() {
        return data.structures();
    }

    public Instant fetchedAt() {
        return Instant.parse(data.fetchedAt());
    }

    public Optional<Category> byId(String id) {
        return Optional.ofNullable(byId.get(id));
    }

    public Structure structureOf(Category category) {
        return structures.get(category.structure());
    }

    /** La struttura con questo nome (la sigla), come la scrive il modello. */
    public Optional<Structure> structureNamed(String name) {
        return data.structures().stream().filter(s -> s.name().equalsIgnoreCase(name)).findFirst();
    }

    // ---------------------------------------------------------------- strutture nominate nel testo

    /**
     * Gli slug delle strutture nominate nel testo, per nome, sigla, alias o corso di studi.
     *
     * <p>Confronta frasi intere: "scienze" da sola non identifica nessuno e "fisicamente" non è
     * "Fisica". Se manca un'espressione il bot fa una domanda in più, che è l'errore meno grave.
     */
    public Set<String> structuresNamedIn(String text) {
        String normalized = " " + normalize(text) + " ";
        Set<String> found = new LinkedHashSet<>();
        structurePhrases.forEach((slug, phrases) -> {
            if (phrases.stream().anyMatch(p -> normalized.contains(" " + p + " "))) {
                found.add(slug);
            }
        });
        return found;
    }

    private static Set<String> phrasesOf(Structure structure) {
        List<String> names = new ArrayList<>(structure.aliases());
        names.add(structure.name());
        if (structure.fullName() != null) {
            names.add(structure.fullName());
            names.add(structure.fullName().replaceFirst("(?i)^Dipartimento di\\s+", ""));
        }
        for (String course : structure.courses()) {
            String name = PARENTHESIS.matcher(course).replaceAll(" ");
            names.add(name);
            String firstPart = normalize(FIRST_PART_END.split(name, 2)[0]);
            if (firstPart.split(" ").length >= 2) {
                names.add(firstPart);
            }
        }
        Set<String> phrases = new LinkedHashSet<>();
        names.stream().map(Catalog::normalize).filter(n -> !n.isEmpty()).forEach(phrases::add);
        return phrases;
    }

    /** Minuscole, senza accenti, punteggiatura ridotta a spazi: "dell'Antichità" = "dell antichita". */
    static String normalize(String text) {
        String decomposed = Normalizer.normalize(text.toLowerCase(Locale.ITALIAN), Normalizer.Form.NFD);
        return NOT_ALPHANUMERIC.matcher(DIACRITICS.matcher(decomposed).replaceAll("")).replaceAll(" ").strip();
    }

    // ---------------------------------------------------------------- testi dei moduli

    /** Le etichette dei campi che caratterizzano questo form, senza quelle presenti ovunque. */
    public List<String> distinctiveLabels(Category category) {
        List<String> labels = new ArrayList<>();
        for (Category.Field field : category.fields()) {
            String label = field.label();
            if (!SYSTEM_FIELDS.contains(field.id()) && !"hidden".equals(field.type())
                    && label.length() >= 4 && label.length() <= 90
                    && labelForms.getOrDefault(label.toLowerCase(Locale.ROOT).strip(), 0) <= MAX_LABEL_FORMS) {
                labels.add(label);
            }
        }
        return labels;
    }

    /** Testo secondario per la ricerca lessicale: campi, opzioni dei menu, avvisi specifici. */
    public String searchDetail(Category category) {
        List<String> parts = new ArrayList<>(distinctiveLabels(category));
        for (Category.Field field : category.fields()) {
            if (!field.options().isEmpty() && field.options().size() <= MAX_OPTIONS_PER_FIELD) {
                parts.addAll(field.options());
            }
        }
        category.notes().stream().filter(n -> !n.boilerplate()).map(Category.Note::text).forEach(parts::add);
        return String.join(". ", parts);
    }

    /** Come ci si può riferire alla struttura di un modulo. */
    public String structureText(Category category) {
        Structure s = structureOf(category);
        List<String> parts = new ArrayList<>(List.of(s.name()));
        if (s.fullName() != null) {
            parts.add(s.fullName());
        }
        parts.addAll(s.aliases());
        parts.addAll(s.courses());
        return String.join(", ", parts);
    }

    /** Testo per l'embedding: breve, così il senso del servizio non si diluisce. */
    public String embeddingText(Category category) {
        StringBuilder text = new StringBuilder(category.name());
        if (!category.summary().isEmpty()) {
            text.append(". ").append(category.summary());
        }
        return text.append(". Struttura: ").append(structureOf(category).label()).toString();
    }
}
