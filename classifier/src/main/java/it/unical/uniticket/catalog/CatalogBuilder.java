package it.unical.uniticket.catalog;

import com.fasterxml.jackson.databind.JsonNode;
import it.unical.uniticket.Json;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;
import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;

/**
 * Costruisce {@code data/catalog.json} a partire dallo scrape in {@code raw_cache}.
 *
 * <p>Un modulo è disponibile se lo scrape ha ricevuto lo schema del suo form (HTTP 200). Gli altri,
 * non attivi (404) o riservati a un profilo diverso da quello dello scrape (403), restano fuori.
 *
 * <p>Il lavoro vero è togliere il rumore: molte descrizioni sono il testo precompilato per chi
 * scrive il ticket ("Descrivi qui...") e molte note sono testo legale identico in tanti form.
 */
public final class CatalogBuilder {

    private static final String PORTAL = "https://ticket.unical.it";

    private static final Pattern PLACEHOLDER_DESCRIPTION = Pattern.compile(
            "^(descrivi|descrivere|dettaglia|inserisci|inserire|insert here|cortesemente|indicare"
                    + "|come possiamo aiutarti|motivare)\\b.*", Pattern.CASE_INSENSITIVE | Pattern.DOTALL);
    private static final Pattern BOILERPLATE_SENTENCE = Pattern.compile(
            "ATTENZIONE: prenderemo in carico la richiesta entro due giorni lavorativi"
                    + " successivi alla presentazione\\.?", Pattern.CASE_INSENSITIVE);
    private static final Pattern LEGAL_NOTE = Pattern.compile(
            "responsabilit\\S* penali|sanzioni penali|trattamento dei (suoi |miei )?dati"
                    + "|dati personali|titolare del trattamento|dichiarazione mendace", Pattern.CASE_INSENSITIVE);
    /** Una nota identica in almeno tanti form è testo standard. */
    private static final int BOILERPLATE_MIN_FORMS = 3;
    private static final Pattern MARKDOWN_LINK = Pattern.compile("!?\\[([^\\]]*)]\\([^)]*\\)");
    private static final Pattern MARKDOWN_MARKS = Pattern.compile("(?m)(^#{1,6}\\s*)|(\\*\\*)|(^\\s*[-*]\\s+)");

    private CatalogBuilder() {
    }

    /** Legge lo scrape e le informazioni curate sulle strutture, scrive il catalogo, riporta i conteggi. */
    public static String run(Path rawCache, Path structureExtras, Path output) {
        JsonNode rawStructures = Json.read(rawCache.resolve("structures.json"));
        JsonNode rawCategories = Json.read(rawCache.resolve("categories.json"));
        JsonNode extras = Json.read(structureExtras);
        List<JsonNode[]> available = new ArrayList<>();
        String fetchedAt = "";
        for (JsonNode category : rawCategories) {
            String structure = category.path("organizational_structure").asText();
            String slug = category.path("slug").asText();
            Path file = rawCache.resolve("forms").resolve(structure + "__" + slug + ".api.json");
            if (!Files.exists(file)) {
                throw new IllegalStateException("Form mancante nello scrape: " + file);
            }
            JsonNode response = Json.read(file);
            String at = response.path("fetchedAt").asText();
            fetchedAt = at.compareTo(fetchedAt) > 0 ? at : fetchedAt;
            if (response.path("statusCode").asInt() == 200) {
                available.add(new JsonNode[] {category, response.path("jsonBody")});
            }
        }

        Map<String, Integer> noteFrequency = new HashMap<>();
        for (JsonNode[] raw : available) {
            Set<String> seen = new LinkedHashSet<>();
            raw[1].path("conditions").forEach(c -> seen.add(noteKey(c.path("fields").path("text").asText(""))));
            seen.forEach(key -> noteFrequency.merge(key, 1, Integer::sum));
        }
        List<Category> categories = new ArrayList<>();
        for (JsonNode[] raw : available) {
            categories.add(toCategory(raw[0], raw[1], noteFrequency, extras));
        }
        categories.sort(Comparator.comparing(Category::id));

        Set<String> used = new LinkedHashSet<>();
        categories.forEach(c -> used.add(c.structure()));
        List<Structure> structures = new ArrayList<>();
        for (JsonNode s : rawStructures) {
            String slug = s.path("slug").asText();
            if (used.contains(slug)) {
                JsonNode extra = extras.path(slug);
                structures.add(new Structure(slug, s.path("name").asText(), extra.path("fullName").asText(null),
                        strings(extra.path("aliases")), strings(extra.path("courses"))));
            }
        }
        structures.sort(Comparator.comparing(Structure::slug));

        Json.writePretty(output, new Catalog.Data(fetchedAt, structures, categories));
        return "Catalogo: %d moduli disponibili su %d, %d strutture"
                .formatted(categories.size(), rawCategories.size(), structures.size());
    }

    private static Category toCategory(JsonNode c, JsonNode form, Map<String, Integer> noteFrequency,
                                       JsonNode extras) {
        String structure = c.path("organizational_structure").asText();
        String slug = c.path("slug").asText();
        String name = collapse(c.path("name").asText());
        boolean departmental = extras.path(structure).path("fullName").asText("").startsWith("Dipartimento");

        List<Category.Note> notes = new ArrayList<>();
        for (JsonNode condition : form.path("conditions")) {
            JsonNode fields = condition.path("fields");
            if (fields.path("is_active").asBoolean(true)) {
                String text = fields.path("text").asText("");
                boolean boilerplate = LEGAL_NOTE.matcher(text).find()
                        || noteFrequency.getOrDefault(noteKey(text), 0) >= BOILERPLATE_MIN_FORMS;
                notes.add(new Category.Note(clean(text), boilerplate));
            }
        }
        List<Category.Field> fields = new ArrayList<>();
        for (JsonNode field : form.path("form")) {
            fields.add(new Category.Field(field.path("id").asText(), collapse(field.path("label").asText("")),
                    field.path("type").asText(""), options(field)));
        }
        return new Category(structure + "/" + slug, structure, name, summary(c.path("description").asText(""), name),
                new Category.Audience(c.path("allow_user").asBoolean(), c.path("allow_employee").asBoolean(),
                        c.path("allow_guest").asBoolean(), c.path("allow_anonymous").asBoolean()),
                c.path("date_start").asText(null), c.path("date_end").asText(null),
                PORTAL + "/tickets/new/" + structure + "/" + slug + "/", departmental, notes, fields);
    }

    /** Vuota se la descrizione non dice nulla sul servizio. */
    static String summary(String description, String name) {
        String text = collapse(BOILERPLATE_SENTENCE.matcher(clean(description)).replaceAll(" "));
        if (text.isEmpty() || text.equalsIgnoreCase(name) || PLACEHOLDER_DESCRIPTION.matcher(text).matches()) {
            return "";
        }
        return text;
    }

    /** Le scelte di un campo: in {@code options} oppure, per select e radio, solo nell'HTML. */
    private static List<String> options(JsonNode field) {
        Set<String> options = new LinkedHashSet<>();
        field.path("options").forEach(o -> options.add(collapse(o.isObject() ? o.path("text").asText("") : o.asText(""))));
        String html = field.path("html").asText("");
        if (html.contains("<option") || html.contains("<input")) {
            Document page = Jsoup.parseBodyFragment(html);
            page.select("option").forEach(o -> options.add(collapse(o.text())));
            page.select("input[type=radio]").forEach(i -> options.add(collapse(i.attr("value"))));
            var boxes = page.select("input[type=checkbox]");
            if (boxes.size() > 1) {
                boxes.forEach(i -> options.add(collapse(i.attr("value"))));
            }
        }
        options.removeIf(o -> o.isEmpty() || o.toLowerCase(Locale.ROOT).startsWith("scegli"));
        return List.copyOf(options);
    }

    /** Confronta solo l'inizio: varianti dello stesso testo legale differiscono nella coda. */
    private static String noteKey(String text) {
        String normalized = collapse(text).toLowerCase(Locale.ROOT);
        return normalized.substring(0, Math.min(90, normalized.length()));
    }

    private static List<String> strings(JsonNode array) {
        List<String> values = new ArrayList<>();
        array.forEach(v -> values.add(v.asText()));
        return values;
    }

    /** Toglie la sintassi markdown e gli spazi superflui. */
    static String clean(String text) {
        String withoutLinks = MARKDOWN_LINK.matcher(text == null ? "" : text).replaceAll("$1");
        return collapse(MARKDOWN_MARKS.matcher(withoutLinks).replaceAll(" "));
    }

    private static String collapse(String text) {
        return text == null ? "" : text.replace('\u00A0', ' ').replaceAll("\\s+", " ").strip();
    }
}
