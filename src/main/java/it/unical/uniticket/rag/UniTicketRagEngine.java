package it.unical.uniticket.rag;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import it.unical.uniticket.access.FormAccess;
import it.unical.uniticket.access.UserProfile;
import it.unical.uniticket.api.dto.CatalogExport;
import it.unical.uniticket.api.dto.CategoryFormSchema;
import it.unical.uniticket.llm.EmbeddingClient;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.text.Normalizer;
import java.util.*;
import java.util.function.Predicate;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/**
 * Ricerca ibrida sul catalogo uniTicket: BM25 ed embeddings fusi con RRF, con i moduli
 * della stessa pratica raggruppati fra strutture diverse.
 */
public class UniTicketRagEngine {

    // Parametri standard Okapi BM25
    private static final double K1 = 1.5;
    private static final double B = 0.75;
    private static final int RRF_K = 60;
    private static final double MIN_EMB_SIMILARITY = 0.30;
    /** Ampiezza fissa, così il ranking non dipende dal K richiesto dal chiamante. */
    private static final int FUSION_POOL_SIZE = 100;
    // Con bge-m3 i titoli normalizzati della stessa pratica superano 0.86, quelli
    // di pratiche diverse restano sotto 0.78.
    private static final double SAME_PRACTICE_SIMILARITY = 0.85;
    private static final String EMBEDDING_INDEX_VERSION = "v6-field-labels-only";

    private static final Set<String> ITALIAN_STOPWORDS = new HashSet<>(Arrays.asList(
            "il", "lo", "la", "i", "gli", "le", "un", "uno", "una", "di", "a", "da", "in", "con",
            "su", "per", "tra", "fra", "del", "dello", "della", "dei", "degli", "delle", "al",
            "allo", "alla", "ai", "agli", "alle", "dal", "dallo", "dalla", "dai", "dagli", "dalle",
            "nel", "nello", "nella", "nei", "negli", "nelle", "sul", "sullo", "sulla", "sui",
            "sugli", "sulle", "che", "chi", "cui", "non", "piu", "quale", "quanto", "quanti",
            "quanta", "quante", "quello", "quelli", "quella", "quelle", "questo", "questi",
            "questa", "queste", "si", "no", "ed", "od", "ma", "se", "perche", "anche", "come",
            "dove", "quando", "mio", "mia", "miei", "mie", "tuo", "tua", "vorrei", "devo", "posso",
            "fare", "avere", "essere", "richiesta", "campo", "opzioni", "note", "modello", "modulo",
            // Parole di riempimento frequenti nelle richieste: senza filtrarle, BM25 premia
            // titoli come "...incarico riguardante attività di tutorato".
            "riguardante", "riguardanti", "riguardo", "inerente", "inerenti", "relativo", "relativa",
            "relativi", "relative", "inviare", "mandare", "qualcosa", "qualche"
    ));

    // Espansione sinonimi di dominio UniCal per aumentare il recall lessicale
    private static final Map<String, List<String>> DOMAIN_SYNONYMS = new HashMap<>();
    private static final Map<String, List<String>> QUERY_TOKEN_ALIASES = new HashMap<>();
    static {
        DOMAIN_SYNONYMS.put("wifi", Arrays.asList("eduroam", "eduroam_cr", "wireless", "rete", "access", "point"));
        DOMAIN_SYNONYMS.put("eduroam", Arrays.asList("wifi", "wi-fi", "wireless", "rete", "centro", "residenziale"));
        DOMAIN_SYNONYMS.put("teams", Arrays.asList("office365", "office", "365", "studenti", "servizimicrosoft"));
        DOMAIN_SYNONYMS.put("inglese", Arrays.asList("cla", "cambridge", "ielts", "toefl", "trinity", "b1", "b2", "c1"));
        DOMAIN_SYNONYMS.put("cambridge", Arrays.asList("cla", "inglese", "certificazioni", "internazionali", "lingua"));
        DOMAIN_SYNONYMS.put("ielts", Arrays.asList("cla", "inglese", "certificazioni", "internazionali", "lingua"));
        DOMAIN_SYNONYMS.put("auto", Arrays.asList("autovettura", "veicolo", "targa", "parcheggio", "quartieri"));
        DOMAIN_SYNONYMS.put("macchina", Arrays.asList("autovettura", "veicolo", "targa", "quartieri", "residenziali"));
        DOMAIN_SYNONYMS.put("mensa", Arrays.asList("ristorazione", "pasto", "centro", "residenziale"));
        DOMAIN_SYNONYMS.put("alloggio", Arrays.asList("alloggi", "stanza", "borsa", "posto", "maisonnettes", "martensson", "chiodo", "molicelle"));
        DOMAIN_SYNONYMS.put("erasmus", Arrays.asList("mobilita", "internazionale", "estero", "biglietto", "rata", "saldo"));
        DOMAIN_SYNONYMS.put("supporto", Arrays.asList("sussidio", "sussidi", "aiuto", "sostegno", "assistenza"));
        DOMAIN_SYNONYMS.put("economico", Arrays.asList("economia", "disagio", "bisogno", "necessita", "contributo", "tasse"));
        DOMAIN_SYNONYMS.put("difficolta", Arrays.asList("disagio", "bisogno", "necessita", "stato di bisogno"));
        DOMAIN_SYNONYMS.put("richiedere", Arrays.asList("domanda", "richiesta"));
        DOMAIN_SYNONYMS.put("borsa", Arrays.asList("sussidio", "beneficio", "diritto allo studio"));
        DOMAIN_SYNONYMS.put("cancellarmi", Arrays.asList("cancellazione", "rinuncia", "chiusura", "cessazione"));
        DOMAIN_SYNONYMS.put("cancellarsi", Arrays.asList("cancellazione", "rinuncia", "chiusura", "cessazione"));
        DOMAIN_SYNONYMS.put("cancellare", Arrays.asList("cancellazione", "rinuncia", "chiusura", "cessazione"));
        DOMAIN_SYNONYMS.put("cancellazione", Arrays.asList("rinuncia", "chiusura", "cessazione"));
        DOMAIN_SYNONYMS.put("extracurriculari", Arrays.asList("extra", "para", "universitarie", "extrauniversitarie"));
        DOMAIN_SYNONYMS.put("extracurricolari", Arrays.asList("extra", "para", "universitarie", "extrauniversitarie"));
        DOMAIN_SYNONYMS.put("email", Arrays.asList("posta", "office365", "studentiunicalit", "webmail"));
        DOMAIN_SYNONYMS.put("posta", Arrays.asList("email", "office365", "studentiunicalit", "webmail"));

        // Correzioni conservative per refusi frequenti nelle richieste in linguaggio naturale.
        QUERY_TOKEN_ALIASES.put("difficiolt", Arrays.asList("difficolt"));
    }

    public static class ScoredCategory {
        public final CategoryFormSchema schema;
        public final double score;
        public final double bm25Score;
        public final double embeddingScore;
        /** Tutte le varianti visibili della pratica, compreso {@link #schema}. */
        public final List<CategoryFormSchema> groupVariants;

        public ScoredCategory(CategoryFormSchema schema, double score) {
            this(schema, score, 0.0, 0.0, Collections.singletonList(schema));
        }

        public ScoredCategory(CategoryFormSchema schema, double score,
                              double bm25Score, double embeddingScore,
                              List<CategoryFormSchema> groupVariants) {
            this.schema = schema;
            this.score = score;
            this.bm25Score = bm25Score;
            this.embeddingScore = embeddingScore;
            this.groupVariants = Collections.unmodifiableList(new ArrayList<>(groupVariants));
        }

        private ScoredCategory withGroupVariants(List<CategoryFormSchema> variants) {
            return new ScoredCategory(schema, score, bm25Score, embeddingScore, variants);
        }
    }

    private final List<CategoryFormSchema> catalog;
    private final Map<String, List<String>> phrasesBySlug;
    private final List<List<String>> docTokens;
    private final Map<String, Integer> docFreq;
    private final double avgDocLength;
    private final Set<String> activeStructureSlugs;
    private final EmbeddingClient embeddingClient;
    private final List<float[]> categoryEmbeddings;
    private final Map<String, List<CategoryFormSchema>> practiceVariants;

    /**
     * @param embeddingClient    se null la ricerca usa solo BM25
     * @param embeddingCacheFile cache degli embeddings, oppure null per non usarla
     * @param phrasesFile        frasi colloquiali per modulo (form_phrases.json), oppure null
     */
    public UniTicketRagEngine(File catalogJsonFile, EmbeddingClient embeddingClient,
                              File embeddingCacheFile, File phrasesFile) throws IOException {
        ObjectMapper mapper = new ObjectMapper();
        CatalogExport export = mapper.readValue(catalogJsonFile, CatalogExport.class);
        this.catalog = export.allTicketsFlat != null ? export.allTicketsFlat : Collections.emptyList();
        this.phrasesBySlug = phrasesFile != null && phrasesFile.isFile()
                ? mapper.readValue(phrasesFile, new TypeReference<Map<String, List<String>>>() { })
                : Collections.emptyMap();
        this.activeStructureSlugs = new HashSet<>();
        for (it.unical.uniticket.api.dto.StructureEntry structure : export.structures) {
            if (structure.active && structure.structureSlug != null) {
                activeStructureSlugs.add(normalizeKey(structure.structureSlug));
            }
        }
        this.docTokens = new ArrayList<>(catalog.size());
        this.docFreq = new HashMap<>();

        long totalLen = 0;
        for (CategoryFormSchema item : catalog) {
            List<String> tokens = tokenize(lexicalDocument(item));
            docTokens.add(tokens);
            totalLen += tokens.size();
            for (String token : new HashSet<>(tokens)) {
                docFreq.merge(token, 1, Integer::sum);
            }
        }
        this.avgDocLength = catalog.isEmpty() ? 1.0 : (double) totalLen / catalog.size();
        this.embeddingClient = embeddingClient;

        EmbeddingIndex index = embeddingClient == null || catalog.isEmpty()
                ? EmbeddingIndex.EMPTY
                : loadOrComputeEmbeddings(fingerprint(catalogJsonFile, phrasesFile), embeddingCacheFile);
        this.categoryEmbeddings = index.documents;
        this.practiceVariants = buildPracticeVariants(index.titles);
    }

    private String lexicalDocument(CategoryFormSchema item) {
        // Peso triplo al titolo e doppio alle note per migliorare il ranking.
        return item.categoryTitle + " " + item.categoryTitle + " " + item.categoryTitle + " "
                + item.structureName + " " + item.structureSlug + " "
                + (item.categoryNotes != null ? item.categoryNotes + " " + item.categoryNotes + " " : "")
                + (item.ragSearchText != null ? item.ragSearchText : "")
                + " " + String.join(" ", phrasesOf(item));
    }

    private List<String> phrasesOf(CategoryFormSchema item) {
        return phrasesBySlug.getOrDefault(item.compositeSlug, Collections.emptyList());
    }

    private static final class EmbeddingIndex {
        private static final EmbeddingIndex EMPTY =
                new EmbeddingIndex(Collections.emptyList(), Collections.emptyList());

        private final List<float[]> documents;
        private final List<float[]> titles;

        private EmbeddingIndex(List<float[]> documents, List<float[]> titles) {
            this.documents = documents;
            this.titles = titles;
        }
    }

    private EmbeddingIndex loadOrComputeEmbeddings(String fingerprint, File cacheFile) {
        if (cacheFile != null) {
            EmbeddingIndex cached = loadEmbeddingCache(cacheFile, fingerprint);
            if (cached != null) {
                System.out.println("✅ Embeddings categorie caricati dalla cache: " + cacheFile.getPath());
                return cached;
            }
        }
        try {
            List<String> documents = new ArrayList<>(catalog.size());
            List<String> titles = new ArrayList<>(catalog.size());
            for (CategoryFormSchema category : catalog) {
                documents.add(embeddingDocument(category));
                titles.add(normalizeTitle(category));
            }
            EmbeddingIndex computed = new EmbeddingIndex(
                    embeddingClient.embedBatch(documents), embeddingClient.embedBatch(titles));
            if (computed.documents.size() != catalog.size() || computed.titles.size() != catalog.size()) {
                throw new IllegalStateException("Numero di embeddings diverso dal catalogo.");
            }
            if (cacheFile != null) saveEmbeddingCache(cacheFile, fingerprint, computed);
            return computed;
        } catch (RuntimeException e) {
            System.err.println("Impossibile calcolare gli embeddings delle categorie: " + e.getMessage());
            return EmbeddingIndex.EMPTY;
        }
    }

    private String embeddingDocument(CategoryFormSchema category) {
        StringBuilder text = new StringBuilder();
        appendEmbeddingPart(text, category.categoryTitle);
        appendEmbeddingPart(text, category.categoryNotes);
        appendEmbeddingPart(text, category.structureName);
        // Le frasi precedono il testo del modulo: sono brevi e rappresentano il bisogno
        // dell'utente, mentre il testo del modulo può essere molto lungo.
        appendEmbeddingPart(text, String.join(" . ", phrasesOf(category)));
        appendEmbeddingPart(text, category.ragSearchText);
        return text.toString();
    }

    private void appendEmbeddingPart(StringBuilder target, String value) {
        if (value == null || value.trim().isEmpty()) return;
        if (target.length() > 0) target.append(" | ");
        target.append(value.trim());
    }

    private EmbeddingIndex loadEmbeddingCache(File cacheFile, String fingerprint) {
        try {
            if (!cacheFile.isFile()) return null;
            JsonNode root = new ObjectMapper().readTree(cacheFile);
            if (!fingerprint.equals(root.path("catalogFingerprint").asText())) return null;
            List<float[]> documents = readVectors(root.path("embeddings"));
            List<float[]> titles = readVectors(root.path("titleEmbeddings"));
            return documents == null || titles == null ? null : new EmbeddingIndex(documents, titles);
        } catch (Exception e) {
            System.err.println("Cache embeddings non utilizzabile: " + e.getMessage());
            return null;
        }
    }

    private List<float[]> readVectors(JsonNode vectors) {
        if (vectors.size() != catalog.size()) return null;
        List<float[]> result = new ArrayList<>(vectors.size());
        for (JsonNode embedding : vectors) {
            if (!embedding.isArray() || embedding.isEmpty()) return null;
            float[] vector = new float[embedding.size()];
            for (int i = 0; i < embedding.size(); i++) {
                vector[i] = (float) embedding.get(i).asDouble();
            }
            result.add(vector);
        }
        return result;
    }

    private void saveEmbeddingCache(File cacheFile, String fingerprint, EmbeddingIndex index) {
        try {
            File parent = cacheFile.getParentFile();
            if (parent != null && !parent.exists() && !parent.mkdirs()) {
                throw new IOException("impossibile creare " + parent);
            }
            ObjectMapper mapper = new ObjectMapper();
            ObjectNode root = mapper.createObjectNode();
            root.put("catalogFingerprint", fingerprint);
            writeVectors(root.putArray("embeddings"), index.documents);
            writeVectors(root.putArray("titleEmbeddings"), index.titles);
            File temporary = new File(cacheFile.getPath() + ".tmp");
            mapper.writeValue(temporary, root);
            try {
                Files.move(temporary.toPath(), cacheFile.toPath(),
                        java.nio.file.StandardCopyOption.REPLACE_EXISTING,
                        java.nio.file.StandardCopyOption.ATOMIC_MOVE);
            } catch (java.nio.file.AtomicMoveNotSupportedException e) {
                Files.move(temporary.toPath(), cacheFile.toPath(),
                        java.nio.file.StandardCopyOption.REPLACE_EXISTING);
            }
        } catch (Exception e) {
            System.err.println("Impossibile salvare la cache embeddings: " + e.getMessage());
        }
    }

    private void writeVectors(ArrayNode target, List<float[]> vectors) {
        for (float[] embedding : vectors) {
            ArrayNode vector = target.addArray();
            for (float value : embedding) vector.add(value);
        }
    }

    private String fingerprint(File catalogJsonFile, File phrasesFile) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            digest.update(Files.readAllBytes(catalogJsonFile.toPath()));
            if (phrasesFile != null && phrasesFile.isFile()) {
                digest.update(Files.readAllBytes(phrasesFile.toPath()));
            }
            StringBuilder result = new StringBuilder();
            for (byte value : digest.digest()) result.append(String.format("%02x", value));
            return result + ":" + EMBEDDING_INDEX_VERSION;
        } catch (Exception e) {
            throw new IllegalStateException("Impossibile calcolare l'impronta del catalogo.", e);
        }
    }

    /**
     * Calcola per ogni modulo le varianti della stessa pratica in altre strutture.
     * Avviene una sola volta qui, così a runtime non servono chiamate di rete e la
     * variante del dipartimento dell'utente è nota anche se il ranking non l'ha trovata.
     */
    private Map<String, List<CategoryFormSchema>> buildPracticeVariants(List<float[]> titleEmbeddings) {
        Map<String, List<CategoryFormSchema>> result = new HashMap<>();
        List<String> titles = catalog.stream().map(this::normalizeTitle).collect(Collectors.toList());
        for (int i = 0; i < catalog.size(); i++) {
            List<CategoryFormSchema> variants = new ArrayList<>();
            variants.add(catalog.get(i));
            for (int j = 0; j < catalog.size(); j++) {
                if (i == j || !differentStructure(catalog.get(i), catalog.get(j))) continue;
                boolean sameTitle = titles.get(i).equalsIgnoreCase(titles.get(j));
                boolean similarTitle = !titleEmbeddings.isEmpty()
                        && EmbeddingUtils.cosine(titleEmbeddings.get(i), titleEmbeddings.get(j))
                        >= SAME_PRACTICE_SIMILARITY;
                if (sameTitle || similarTitle) variants.add(catalog.get(j));
            }
            result.put(catalog.get(i).compositeSlug, variants);
        }
        return result;
    }

    /**
     * Cerca tra tutti i moduli visibili all'utente, compresi quelli chiusi.
     *
     * @param topK     numero massimo di pratiche restituite
     * @param profile  decide quali moduli sono visibili; il dipartimento non influenza il ranking
     * @param excluded slug già rifiutati dall'utente
     */
    public List<ScoredCategory> search(String query, int topK, UserProfile profile, Set<String> excluded) {
        return rank(query, topK, profile, excluded, form -> true);
    }

    /**
     * Classifica solo i moduli aperti, così un modulo chiuso e simile non può superare quello
     * giusto. Le varianti di ogni pratica comprendono comunque quelle chiuse: se quella del
     * dipartimento dell'utente è chiusa, non deve sembrare inesistente.
     */
    public List<ScoredCategory> searchOpen(String query, int topK, UserProfile profile, Set<String> excluded) {
        return rank(query, topK, profile, excluded, form -> FormAccess.of(form, profile) == FormAccess.OPEN);
    }

    private List<ScoredCategory> rank(String query, int topK, UserProfile profile, Set<String> excluded,
                                      Predicate<CategoryFormSchema> rankable) {
        Predicate<CategoryFormSchema> visible = form -> isVisible(form, profile)
                && !excluded.contains(form.compositeSlug);
        Predicate<CategoryFormSchema> ranked = visible.and(rankable);
        List<ScoredCategory> lexical = rankLexical(query, ranked);
        List<ScoredCategory> results = lexical;
        if (embeddingClient != null && !categoryEmbeddings.isEmpty()) {
            try {
                results = fuseRankings(lexical, rankSemantic(query, ranked));
            } catch (RuntimeException e) {
                System.err.println("Fallback a BM25 puro: " + e.getMessage());
            }
        }
        return clusterPractices(results, topK, visible);
    }

    private boolean isVisible(CategoryFormSchema form, UserProfile profile) {
        boolean activeStructure = activeStructureSlugs.isEmpty()
                || activeStructureSlugs.contains(normalizeKey(form.structureSlug));
        FormAccess access = FormAccess.of(form, profile);
        return activeStructure && (access == FormAccess.OPEN || access == FormAccess.CLOSED);
    }

    private List<ScoredCategory> rankLexical(String userQuery, Predicate<CategoryFormSchema> visible) {
        List<String> expandedQueryTokens = expandQuery(userQuery);
        List<ScoredCategory> results = new ArrayList<>();
        int N = catalog.size();

        for (int i = 0; i < N; i++) {
            CategoryFormSchema schema = catalog.get(i);
            if (!visible.test(schema)) continue;
            List<String> dTokens = docTokens.get(i);
            if (dTokens.isEmpty()) continue;

            Map<String, Integer> termFreq = new HashMap<>();
            for (String t : dTokens) termFreq.merge(t, 1, Integer::sum);

            double score = 0.0;
            int docLen = dTokens.size();
            for (String qToken : expandedQueryTokens) {
                int tf = termFreq.getOrDefault(qToken, 0);
                if (tf == 0) continue;
                int df = docFreq.getOrDefault(qToken, 0);
                double idf = Math.log(1.0 + (N - df + 0.5) / (df + 0.5));
                double numerator = tf * (K1 + 1.0);
                double denominator = tf + K1 * (1.0 - B + B * (docLen / avgDocLength));
                score += idf * (numerator / denominator);
            }
            if (score > 0) {
                results.add(new ScoredCategory(schema, score, score, 0.0,
                        Collections.singletonList(schema)));
            }
        }
        results.sort((a, b) -> Double.compare(b.score, a.score));
        return results.stream().limit(FUSION_POOL_SIZE).collect(Collectors.toList());
    }

    private List<String> expandQuery(String userQuery) {
        List<String> baseTokens = tokenize(userQuery);
        List<String> normalizedTokens = new ArrayList<>(baseTokens);
        for (String token : baseTokens) {
            normalizedTokens.addAll(QUERY_TOKEN_ALIASES.getOrDefault(token, Collections.emptyList()));
        }
        Set<String> expanded = new LinkedHashSet<>(normalizedTokens);
        // Stemma sia le chiavi sia i valori del dizionario: la query e i documenti
        // sono stemmati, quindi confrontare termini non normalizzati fa perdere
        // espansioni come "supporto" -> "sussidio".
        for (Map.Entry<String, List<String>> synonym : DOMAIN_SYNONYMS.entrySet()) {
            List<String> synonymKeys = tokenize(synonym.getKey());
            if (normalizedTokens.stream().anyMatch(synonymKeys::contains)) {
                synonym.getValue().stream()
                        .flatMap(value -> tokenize(value).stream())
                        .forEach(expanded::add);
            }
        }
        return new ArrayList<>(expanded);
    }

    private List<ScoredCategory> rankSemantic(String userQuery, Predicate<CategoryFormSchema> visible) {
        float[] queryVector = embeddingClient.embed(userQuery);
        List<ScoredCategory> results = new ArrayList<>();
        for (int i = 0; i < catalog.size(); i++) {
            CategoryFormSchema schema = catalog.get(i);
            if (!visible.test(schema)) continue;
            double score = EmbeddingUtils.cosine(queryVector, categoryEmbeddings.get(i));
            if (score >= MIN_EMB_SIMILARITY) {
                results.add(new ScoredCategory(schema, score, 0.0, score,
                        Collections.singletonList(schema)));
            }
        }
        results.sort((a, b) -> Double.compare(b.score, a.score));
        return results.stream().limit(FUSION_POOL_SIZE).collect(Collectors.toList());
    }

    private List<ScoredCategory> fuseRankings(List<ScoredCategory> first, List<ScoredCategory> second) {
        Map<String, ScoredCategory> candidates = new HashMap<>();
        addRanking(candidates, first);
        addRanking(candidates, second);
        return candidates.values().stream()
                .sorted((a, b) -> Double.compare(b.score, a.score))
                .collect(Collectors.toList());
    }

    private void addRanking(Map<String, ScoredCategory> candidates, List<ScoredCategory> ranking) {
        for (int rank = 0; rank < ranking.size(); rank++) {
            ScoredCategory candidate = ranking.get(rank);
            double rrf = 1.0 / (RRF_K + rank + 1);
            candidates.merge(candidate.schema.compositeSlug,
                    new ScoredCategory(candidate.schema, rrf, candidate.bm25Score,
                            candidate.embeddingScore, candidate.groupVariants),
                    (a, b) -> new ScoredCategory(a.schema, a.score + b.score,
                            Math.max(a.bm25Score, b.bm25Score),
                            Math.max(a.embeddingScore, b.embeddingScore),
                            a.groupVariants));
        }
    }

    /** Ogni pratica occupa un solo posto nel top-K, rappresentata dal modulo meglio classificato. */
    private List<ScoredCategory> clusterPractices(List<ScoredCategory> ranked, int topK,
                                                  Predicate<CategoryFormSchema> visible) {
        Set<String> covered = new HashSet<>();
        List<ScoredCategory> practices = new ArrayList<>();
        for (ScoredCategory candidate : ranked) {
            if (practices.size() == topK) break;
            if (covered.contains(candidate.schema.compositeSlug)) continue;
            List<CategoryFormSchema> variants = variantsOf(candidate.schema).stream()
                    .filter(visible)
                    .collect(Collectors.toList());
            variants.forEach(variant -> covered.add(variant.compositeSlug));
            practices.add(candidate.withGroupVariants(variants));
        }
        return practices;
    }

    private List<CategoryFormSchema> variantsOf(CategoryFormSchema form) {
        return practiceVariants.getOrDefault(form.compositeSlug, Collections.singletonList(form));
    }

    private boolean differentStructure(CategoryFormSchema first, CategoryFormSchema second) {
        return !Objects.equals(normalizeKey(first.structureSlug), normalizeKey(second.structureSlug));
    }

    private String normalizeKey(String value) {
        return value == null ? "" : value.trim().toLowerCase(Locale.ROOT);
    }

    /**
     * Toglie dal titolo le parti tra parentesi e il nome della struttura, che di solito
     * contengono solo corso o dipartimento.
     */
    private String normalizeTitle(CategoryFormSchema schema) {
        String title = schema.categoryTitle == null ? "" : schema.categoryTitle.replaceAll("\\([^)]*\\)", " ");
        if (schema.structureName != null && !schema.structureName.trim().isEmpty()) {
            title = title.replaceAll("(?i)\\b" + Pattern.quote(schema.structureName.trim()) + "\\b", " ");
        }
        return title.replaceAll("[\\s\\-–]+$", "").replaceAll("\\s+", " ").trim();
    }

    public Optional<CategoryFormSchema> findByCompositeSlug(String compositeSlug) {
        return catalog.stream()
                .filter(c -> c.compositeSlug.equalsIgnoreCase(compositeSlug))
                .findFirst();
    }

    private List<String> tokenize(String text) {
        if (text == null || text.isEmpty()) return Collections.emptyList();

        // Rimuove accenti e normalizza in minuscolo
        String normalized = Normalizer.normalize(text.toLowerCase(Locale.ITALIAN), Normalizer.Form.NFD)
                .replaceAll("\\p{InCombiningDiacriticalMarks}+", "");

        normalized = normalized.replaceAll("(?i)\\b(?:l|dell|all|dall|nell|sull|un|quest|quell|d)['’]", "");
        String[] rawTokens = normalized.split("[^a-z0-9_]+");
        List<String> cleanTokens = new ArrayList<>();

        for (String token : rawTokens) {
            if (token.length() < 2) continue;
            if (ITALIAN_STOPWORDS.contains(token)) continue;
            cleanTokens.add(stemItalianLight(token));
        }
        return cleanTokens;
    }

    /**
     * Stemmer leggero per la lingua italiana (unifica singolari/plurali/coniugazioni comuni).
     */
    private String stemItalianLight(String word) {
        if (word.length() <= 4) return word;
        if (word.endsWith("chi") || word.endsWith("che")) {
            return word.substring(0, word.length() - 3) + "c";
        }
        if (word.endsWith("ghi") || word.endsWith("ghe")) {
            return word.substring(0, word.length() - 3) + "g";
        }
        if (word.endsWith("zioni") || word.endsWith("zione")) {
            return word.substring(0, word.length() - 5) + "zion";
        }
        if (word.endsWith("menti") || word.endsWith("mento")) {
            return word.substring(0, word.length() - 5) + "ment";
        }
        // "studio" e "studi" devono avere la stessa radice.
        if (word.length() > 5 && (word.endsWith("io") || word.endsWith("ii"))) {
            return word.substring(0, word.length() - 2);
        }
        char last = word.charAt(word.length() - 1);
        if (last == 'a' || last == 'e' || last == 'i' || last == 'o') {
            return word.substring(0, word.length() - 1);
        }
        return word;
    }
}
