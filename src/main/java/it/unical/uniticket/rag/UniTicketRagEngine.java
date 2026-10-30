package it.unical.uniticket.rag;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import it.unical.uniticket.api.dto.CatalogExport;
import it.unical.uniticket.api.dto.CategoryFormSchema;
import it.unical.uniticket.llm.EmbeddingClient;

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.text.Normalizer;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

public class UniTicketRagEngine {

    private final List<CategoryFormSchema> catalog;
    private final List<List<String>> docTokens;
    private final Map<String, Integer> docFreq;
    private final double avgDocLength;
    private final List<List<String>> catalogDocTokens;
    private final Map<String, Integer> catalogDocFreq;
    private final double catalogAvgDocLength;
    private final Set<String> activeStructureSlugs;
    private final Map<String, TaxonomyMetadata> taxonomyBySlug;
    private final EmbeddingClient embeddingClient;
    private final List<float[]> categoryEmbeddings;
    private final Map<String, float[]> titleEmbeddingCache = new ConcurrentHashMap<>();
    private final boolean useStopwords;
    private final boolean useDomainSynonyms;

    // Parametri standard Okapi BM25
    private static final double K1 = 1.5;
    private static final double B = 0.75;
    private static final int RRF_K = 60;
    private static final double MIN_EMB_SIMILARITY = 0.30;
    private static final String EMBEDDING_INDEX_VERSION = "v4-rag-search-text-after-core-fields";

    private static class TaxonomyMetadata {
        private final String domain;
        private final String lifecycle;
        private final String serviceFamily;
        private final List<String> ruleMatches;
        private final List<String> userAliases;

        private TaxonomyMetadata(String domain, String lifecycle, String serviceFamily,
                                 List<String> ruleMatches, List<String> userAliases) {
            this.domain = domain;
            this.lifecycle = lifecycle;
            this.serviceFamily = serviceFamily;
            this.ruleMatches = ruleMatches;
            this.userAliases = userAliases;
        }

        private String asSearchText() {
            return String.join(" ", domain, lifecycle, serviceFamily,
                    String.join(" ", ruleMatches), String.join(" ", userAliases));
        }
    }

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

        // Correzioni conservative per refusi frequenti nelle richieste in linguaggio naturale.
        QUERY_TOKEN_ALIASES.put("difficiolt", Arrays.asList("difficolt"));
    }

    public static class ScoredCategory {
        public final CategoryFormSchema schema;
        public final double score;
        public final double rrfScore;
        public final double bm25Score;
        public final double embeddingScore;
        public final List<CategoryFormSchema> groupVariants;

        public ScoredCategory(CategoryFormSchema schema, double score) {
            this(schema, score, 0.0, 0.0, 0.0, Collections.emptyList());
        }

        private ScoredCategory(CategoryFormSchema schema, double score,
                               double rrfScore, double bm25Score, double embeddingScore,
                               List<CategoryFormSchema> groupVariants) {
            this.schema = schema;
            this.score = score;
            this.rrfScore = rrfScore;
            this.bm25Score = bm25Score;
            this.embeddingScore = embeddingScore;
            this.groupVariants = Collections.unmodifiableList(new ArrayList<>(groupVariants));
        }

        private ScoredCategory withGroupVariants(List<CategoryFormSchema> variants) {
            return new ScoredCategory(schema, score, rrfScore, bm25Score, embeddingScore, variants);
        }
    }

    public UniTicketRagEngine(File catalogJsonFile) throws IOException {
        this(catalogJsonFile, null, true, true);
    }

    public UniTicketRagEngine(File catalogJsonFile, EmbeddingClient embeddingClient) throws IOException {
        this(catalogJsonFile, embeddingClient, true, true);
    }

    /**
     * Crea il motore RAG permettendo di valutare separatamente l'effetto delle
     * normalizzazioni lessicali sul ranking BM25.
     *
     * <p>Gli embeddings non vengono modificati da questi flag: ricevono sempre
     * il testo originale delle categorie e della query.</p>
     *
     * @param useStopwords      se false, conserva tutte le parole nella tokenizzazione BM25
     * @param useDomainSynonyms se false, disabilita l'espansione dei sinonimi di dominio
     */
    public UniTicketRagEngine(File catalogJsonFile, EmbeddingClient embeddingClient,
                             boolean useStopwords, boolean useDomainSynonyms) throws IOException {
        this(catalogJsonFile, embeddingClient, useStopwords, useDomainSynonyms, null);
    }

    public UniTicketRagEngine(File catalogJsonFile, EmbeddingClient embeddingClient,
                             boolean useStopwords, boolean useDomainSynonyms,
                             File embeddingCacheFile) throws IOException {
        this(catalogJsonFile, embeddingClient, useStopwords, useDomainSynonyms,
                embeddingCacheFile, null);
    }

    public UniTicketRagEngine(File catalogJsonFile, EmbeddingClient embeddingClient,
                             boolean useStopwords, boolean useDomainSynonyms,
                             File embeddingCacheFile, File taxonomyJsonFile) throws IOException {
        ObjectMapper mapper = new ObjectMapper();
        CatalogExport export = mapper.readValue(catalogJsonFile, CatalogExport.class);
        this.catalog = export.allTicketsFlat != null ? export.allTicketsFlat : Collections.emptyList();
        this.useStopwords = useStopwords;
        this.useDomainSynonyms = useDomainSynonyms;
        this.taxonomyBySlug = loadTaxonomy(mapper, taxonomyJsonFile);
        this.activeStructureSlugs = new HashSet<>();
        for (it.unical.uniticket.api.dto.StructureEntry structure : export.structures) {
            if (structure.active && structure.structureSlug != null) {
                activeStructureSlugs.add(structure.structureSlug.toLowerCase(Locale.ROOT));
            }
        }
        this.docTokens = new ArrayList<>(catalog.size());
        this.docFreq = new HashMap<>();
        this.catalogDocTokens = new ArrayList<>(catalog.size());
        this.catalogDocFreq = new HashMap<>();

        long totalLen = 0;
        long catalogTotalLen = 0;
        for (CategoryFormSchema item : catalog) {
            // Diamo peso triplo al titolo della categoria e doppio alle note per migliorare il ranking
            String weightedCorpus = (item.categoryTitle + " " + item.categoryTitle + " " + item.categoryTitle + " ")
                    + (item.structureName + " " + item.structureSlug + " ")
                    + (item.categoryNotes != null ? item.categoryNotes + " " + item.categoryNotes + " " : "")
                    + (item.ragSearchText != null ? item.ragSearchText : "")
                    + (item.jevCriterionSummary != null ? " " + item.jevCriterionSummary : "")
                    + taxonomySearchText(item);

            List<String> tokens = tokenize(weightedCorpus);
            docTokens.add(tokens);
            totalLen += tokens.size();
            String catalogCorpus = (item.categoryTitle + " " + item.categoryTitle + " " + item.categoryTitle + " ")
                    + (item.structureName + " " + item.structureSlug + " ")
                    + (item.categoryNotes != null ? item.categoryNotes + " " + item.categoryNotes + " " : "")
                    + (item.ragSearchText != null ? item.ragSearchText : "")
                    + (item.jevCriterionSummary != null ? " " + item.jevCriterionSummary : "");
            List<String> catalogTokens = tokenize(catalogCorpus);
            catalogDocTokens.add(catalogTokens);
            catalogTotalLen += catalogTokens.size();

            Set<String> uniqueTokens = new HashSet<>(tokens);
            for (String token : uniqueTokens) {
                docFreq.put(token, docFreq.getOrDefault(token, 0) + 1);
            }
            for (String token : new HashSet<>(catalogTokens)) {
                catalogDocFreq.put(token, catalogDocFreq.getOrDefault(token, 0) + 1);
            }
        }
        this.avgDocLength = catalog.isEmpty() ? 1.0 : (double) totalLen / catalog.size();
        this.catalogAvgDocLength = catalog.isEmpty() ? 1.0 : (double) catalogTotalLen / catalog.size();
        this.embeddingClient = embeddingClient;
        this.categoryEmbeddings = embeddingClient == null || catalog.isEmpty()
                ? Collections.emptyList() : loadOrComputeCategoryEmbeddings(catalogJsonFile, embeddingCacheFile);
    }

    private Map<String, TaxonomyMetadata> loadTaxonomy(ObjectMapper mapper, File taxonomyJsonFile) {
        if (taxonomyJsonFile == null || !taxonomyJsonFile.isFile()) {
            return Collections.emptyMap();
        }
        try {
            JsonNode root = mapper.readTree(taxonomyJsonFile);
            Map<String, TaxonomyMetadata> result = new HashMap<>();
            for (JsonNode node : root.path("nodes")) {
                if (!"service".equals(node.path("type").asText())) continue;
                JsonNode inferred = node.path("inferred");
                List<String> ruleMatches = new ArrayList<>();
                inferred.path("domainRuleMatches").forEach(value -> ruleMatches.add(value.asText()));
                inferred.path("lifecycleRuleMatches").forEach(value -> ruleMatches.add(value.asText()));
                List<String> userAliases = new ArrayList<>();
                inferred.path("userAliases").forEach(value -> userAliases.add(value.asText()));
                result.put(node.path("compositeSlug").asText(),
                        new TaxonomyMetadata(
                                inferred.path("domain").asText(""),
                                inferred.path("lifecycle").asText(""),
                                inferred.path("serviceFamily").asText(""),
                                ruleMatches, userAliases));
            }
            System.out.println("✅ Tassonomia caricata: " + result.size()
                    + " servizi da " + taxonomyJsonFile.getPath());
            return result;
        } catch (IOException | RuntimeException e) {
            System.err.println("Tassonomia non utilizzabile: " + e.getMessage());
            return Collections.emptyMap();
        }
    }

    private String taxonomySearchText(CategoryFormSchema item) {
        TaxonomyMetadata metadata = taxonomyBySlug.get(item.compositeSlug);
        return metadata == null ? "" : " " + metadata.asSearchText();
    }

    private List<float[]> loadOrComputeCategoryEmbeddings(File catalogJsonFile, File cacheFile) {
        String fingerprint = catalogFingerprint(catalogJsonFile) + ":" + EMBEDDING_INDEX_VERSION;
        if (cacheFile != null) {
            List<float[]> cached = loadEmbeddingCache(cacheFile, fingerprint);
            if (cached != null) {
                System.out.println("✅ Embeddings categorie caricati dalla cache: "
                        + cacheFile.getPath());
                return cached;
            }
        }
        List<float[]> computed = precomputeCategoryEmbeddings();
        if (!computed.isEmpty() && cacheFile != null) {
            saveEmbeddingCache(cacheFile, fingerprint, computed);
        }
        return computed;
    }

    private List<float[]> precomputeCategoryEmbeddings() {
        List<String> texts = new ArrayList<>(catalog.size());
        for (CategoryFormSchema category : catalog) {
            StringBuilder text = new StringBuilder();
            appendEmbeddingPart(text, category.categoryTitle);
            appendEmbeddingPart(text, category.categoryNotes);
            appendEmbeddingPart(text, category.structureName);
            appendEmbeddingPart(text, category.ragSearchText);
            texts.add(text.toString());
        }
        try {
            List<float[]> vectors = embeddingClient.embedBatch(texts);
            if (vectors.size() != catalog.size()) {
                throw new IllegalStateException("Numero di embeddings diverso dal catalogo.");
            }
            return vectors;
        } catch (RuntimeException e) {
            System.err.println("Impossibile calcolare gli embeddings delle categorie: " + e.getMessage());
            return Collections.emptyList();
        }
    }

    private void appendEmbeddingPart(StringBuilder target, String value) {
        if (value == null || value.trim().isEmpty()) return;
        if (target.length() > 0) target.append(" | ");
        target.append(value.trim());
    }

    private List<float[]> loadEmbeddingCache(File cacheFile, String fingerprint) {
        try {
            if (!cacheFile.isFile()) return null;
            ObjectMapper mapper = new ObjectMapper();
            JsonNode root = mapper.readTree(cacheFile);
            if (!fingerprint.equals(root.path("catalogFingerprint").asText())
                    || root.path("embeddings").size() != catalog.size()) {
                return null;
            }
            List<float[]> result = new ArrayList<>();
            for (JsonNode embedding : root.path("embeddings")) {
                if (!embedding.isArray() || embedding.isEmpty()) return null;
                float[] vector = new float[embedding.size()];
                for (int i = 0; i < embedding.size(); i++) {
                    vector[i] = (float) embedding.get(i).asDouble();
                }
                result.add(vector);
            }
            return result;
        } catch (Exception e) {
            System.err.println("Cache embeddings non utilizzabile: " + e.getMessage());
            return null;
        }
    }

    private void saveEmbeddingCache(File cacheFile, String fingerprint, List<float[]> embeddings) {
        try {
            File parent = cacheFile.getParentFile();
            if (parent != null && !parent.exists() && !parent.mkdirs()) {
                throw new IOException("impossibile creare " + parent);
            }
            ObjectMapper mapper = new ObjectMapper();
            ObjectNode root = mapper.createObjectNode();
            root.put("catalogFingerprint", fingerprint);
            ArrayNode values = root.putArray("embeddings");
            for (float[] embedding : embeddings) {
                ArrayNode vector = values.addArray();
                for (float value : embedding) vector.add(value);
            }
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

    private String catalogFingerprint(File catalogJsonFile) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(Files.readAllBytes(catalogJsonFile.toPath()));
            StringBuilder result = new StringBuilder();
            for (byte value : digest) result.append(String.format("%02x", value));
            return result.toString();
        } catch (Exception e) {
            throw new IllegalStateException("Impossibile calcolare l'impronta del catalogo.", e);
        }
    }

    /**
     * Restituisce i Top-K moduli più rilevanti per la query dell'utente.
     *
     * @param userQuery          Domanda in linguaggio naturale dell'utente
     * @param topK               Numero massimo di candidati da passare a JEV (consigliato: 5 - 8)
     * @param onlyAccessible     Parametro mantenuto per compatibilità; la ricerca principale
     *                           filtra sempre i moduli non selezionabili
     */
    public List<ScoredCategory> searchTopK(String userQuery, int topK, boolean onlyAccessible) {
        return searchTopKInternal(userQuery, topK, onlyAccessible, true);
    }

    private List<ScoredCategory> searchTopKInternal(String userQuery, int topK,
                                                     boolean onlyAccessible,
                                                     boolean includeTaxonomy) {
        List<String> baseQueryTokens = tokenize(userQuery);
        List<String> normalizedQueryTokens = new ArrayList<>(baseQueryTokens);
        for (String token : baseQueryTokens) {
            normalizedQueryTokens.addAll(QUERY_TOKEN_ALIASES.getOrDefault(token, Collections.emptyList()));
        }
        Set<String> expandedQueryTokenSet = new LinkedHashSet<>(normalizedQueryTokens);

        if (useDomainSynonyms) {
            // Stemma sia le chiavi sia i valori del dizionario: la query e i documenti
            // sono stemmati, quindi confrontare termini non normalizzati fa perdere
            // espansioni come "supporto" -> "sussidio".
            for (Map.Entry<String, List<String>> synonym : DOMAIN_SYNONYMS.entrySet()) {
                List<String> synonymKeys = tokenize(synonym.getKey());
                if (normalizedQueryTokens.stream().anyMatch(synonymKeys::contains)) {
                    synonym.getValue().stream()
                            .flatMap(value -> tokenize(value).stream())
                            .forEach(expandedQueryTokenSet::add);
                }
            }
        }
        List<String> expandedQueryTokens = new ArrayList<>(expandedQueryTokenSet);

        List<ScoredCategory> results = new ArrayList<>();
        int N = catalog.size();

        for (int i = 0; i < N; i++) {
            CategoryFormSchema schema = catalog.get(i);
            if (!isSelectable(schema)) {
                continue;
            }

            List<List<String>> tokenIndex = includeTaxonomy ? docTokens : catalogDocTokens;
            Map<String, Integer> frequencyIndex = includeTaxonomy ? docFreq : catalogDocFreq;
            double documentAverageLength = includeTaxonomy ? avgDocLength : catalogAvgDocLength;
            List<String> dTokens = tokenIndex.get(i);
            if (dTokens.isEmpty()) continue;

            Map<String, Integer> termFreq = new HashMap<>();
            for (String t : dTokens) {
                termFreq.put(t, termFreq.getOrDefault(t, 0) + 1);
            }

            double score = 0.0;
            int docLen = dTokens.size();

            for (String qToken : expandedQueryTokens) {
                int tf = termFreq.getOrDefault(qToken, 0);
                if (tf == 0) continue;

                int df = frequencyIndex.getOrDefault(qToken, 0);
                double idf = Math.log(1.0 + (N - df + 0.5) / (df + 0.5));
                double numerator = tf * (K1 + 1.0);
                double denominator = tf + K1 * (1.0 - B + B * (docLen / documentAverageLength));

                score += idf * (numerator / denominator);
            }

            if (score > 0) {
                results.add(new ScoredCategory(schema, score, 0.0, score, 0.0,
                        Collections.emptyList()));
            }
        }

        results.sort((a, b) -> Double.compare(b.score, a.score));
        double maximum = results.isEmpty() ? 1.0 : results.get(0).score;
        return results.stream()
                .map(result -> new ScoredCategory(result.schema, result.score, 0.0,
                        result.score / maximum, 0.0, Collections.emptyList()))
                .limit(topK)
                .collect(Collectors.toList());
    }

    public List<ScoredCategory> searchTopKHybrid(String userQuery, int topK, boolean onlyAccessible) {
        if (embeddingClient == null || categoryEmbeddings.isEmpty()) {
            return searchTopK(userQuery, topK, onlyAccessible);
        }
        try {
            int poolSize = Math.max(topK * 6, 30);
            return fuseRRF(searchTopKInternal(userQuery, poolSize, onlyAccessible, false),
                    searchTopKEmbedding(userQuery, poolSize, onlyAccessible), topK);
        } catch (RuntimeException e) {
            System.err.println("Fallback a BM25 puro: " + e.getMessage());
            return searchTopK(userQuery, topK, onlyAccessible);
        }
    }

    private List<ScoredCategory> searchTopKEmbedding(String userQuery, int topK, boolean onlyAccessible) {
        float[] queryVector = embeddingClient.embed(userQuery);
        List<ScoredCategory> results = new ArrayList<>();
        for (int i = 0; i < catalog.size(); i++) {
            CategoryFormSchema schema = catalog.get(i);
            if (!isSelectable(schema)) continue;
            double score = EmbeddingUtils.cosine(queryVector, categoryEmbeddings.get(i));
            if (score >= MIN_EMB_SIMILARITY) {
                results.add(new ScoredCategory(schema, score, 0.0, 0.0, score,
                        Collections.emptyList()));
            }
        }
        results.sort((a, b) -> Double.compare(b.score, a.score));
        return results.stream().limit(topK).collect(Collectors.toList());
    }

    private List<ScoredCategory> fuseRRF(List<ScoredCategory> first, List<ScoredCategory> second, int topK) {
        Map<String, ScoredCategory> candidates = new HashMap<>();
        for (int rank = 0; rank < first.size(); rank++) {
            ScoredCategory candidate = first.get(rank);
            String slug = candidate.schema.compositeSlug;
            double rrf = 1.0 / (RRF_K + rank + 1);
            candidates.merge(slug, new ScoredCategory(candidate.schema, rrf, rrf,
                    candidate.bm25Score, candidate.embeddingScore, Collections.emptyList()),
                    (oldValue, newValue) -> mergeScores(oldValue, newValue));
        }
        for (int rank = 0; rank < second.size(); rank++) {
            ScoredCategory candidate = second.get(rank);
            String slug = candidate.schema.compositeSlug;
            double rrf = 1.0 / (RRF_K + rank + 1);
            candidates.merge(slug, new ScoredCategory(candidate.schema, rrf, rrf,
                    candidate.bm25Score, candidate.embeddingScore, Collections.emptyList()),
                    (oldValue, newValue) -> mergeScores(oldValue, newValue));
        }
        List<ScoredCategory> ranked = candidates.values().stream()
                .sorted((a, b) -> Double.compare(b.score, a.score))
                .collect(Collectors.toList());
        return clusterBeforeTopK(ranked, topK);
    }

    private ScoredCategory mergeScores(ScoredCategory first, ScoredCategory second) {
        return new ScoredCategory(first.schema, first.score + second.score,
                first.rrfScore + second.rrfScore,
                Math.max(first.bm25Score, second.bm25Score),
                Math.max(first.embeddingScore, second.embeddingScore),
                Collections.emptyList());
    }

    private List<ScoredCategory> clusterBeforeTopK(List<ScoredCategory> ranked, int topK) {
        List<ScoredCategory> representatives = new ArrayList<>();
        for (ScoredCategory candidate : ranked) {
            ScoredCategory matching = null;
            for (ScoredCategory representative : representatives) {
                if (!differentStructure(candidate.schema, representative.schema)) continue;
                if (samePractice(candidate.schema, representative.schema)) {
                    matching = representative;
                    break;
                }
            }
            if (matching == null) {
                representatives.add(candidate);
            } else if (candidate.score > matching.score) {
                int index = representatives.indexOf(matching);
                representatives.set(index, candidate);
            }
        }

        List<ScoredCategory> clustered = new ArrayList<>();
        for (ScoredCategory representative : representatives) {
            List<CategoryFormSchema> variants = new ArrayList<>();
            for (ScoredCategory candidate : ranked) {
                if (samePractice(candidate.schema, representative.schema)) {
                    variants.add(candidate.schema);
                }
            }
            clustered.add(representative.withGroupVariants(variants));
        }
        clustered.sort((a, b) -> Double.compare(b.score, a.score));
        return clustered.stream().limit(topK).collect(Collectors.toList());
    }

    private boolean samePractice(CategoryFormSchema first, CategoryFormSchema second) {
        String firstTitle = normalizeTitle(first);
        String secondTitle = normalizeTitle(second);
        if (firstTitle.equalsIgnoreCase(secondTitle)) return true;
        return titleSimilarity(first, second) >= 0.85;
    }

    private boolean differentStructure(CategoryFormSchema first, CategoryFormSchema second) {
        return !Objects.equals(normalizeKey(first.structureSlug), normalizeKey(second.structureSlug));
    }

    private String normalizeKey(String value) {
        return value == null ? "" : value.trim().toLowerCase(Locale.ROOT);
    }

    private boolean isSelectable(CategoryFormSchema schema) {
        return schema.accessible
                && (activeStructureSlugs.isEmpty()
                || activeStructureSlugs.contains(normalizeKey(schema.structureSlug)));
    }

    /**
     * Fallback esplicito per diagnostica e messaggi informativi: non fa parte
     * del pool principale passato al router.
     */
    public List<ScoredCategory> searchTopKIncludingInaccessible(String userQuery, int topK) {
        List<ScoredCategory> results = new ArrayList<>();
        for (int i = 0; i < catalog.size(); i++) {
            CategoryFormSchema schema = catalog.get(i);
            List<String> tokens = docTokens.get(i);
            if (tokens.isEmpty()) continue;
            Set<String> queryTokens = new HashSet<>(tokenize(userQuery));
            long matches = tokens.stream().filter(queryTokens::contains).count();
            if (matches > 0) {
                results.add(new ScoredCategory(schema, matches, 0.0, matches, 0.0,
                        Collections.emptyList()));
            }
        }
        results.sort((a, b) -> Double.compare(b.score, a.score));
        return results.stream().limit(topK).collect(Collectors.toList());
    }

    /**
     * Similarità semantica tra i titoli di due moduli, ignorando le parti tra parentesi
     * e il nome della struttura, che di solito contengono solo corso o dipartimento.
     * Restituisce -1 se gli embeddings non sono disponibili.
     */
    public double titleSimilarity(CategoryFormSchema a, CategoryFormSchema b) {
        if (embeddingClient == null || categoryEmbeddings.isEmpty()) return -1.0;
        try {
            float[] first = titleEmbeddingCache.computeIfAbsent(a.compositeSlug,
                    slug -> embeddingClient.embed(normalizeTitle(a)));
            float[] second = titleEmbeddingCache.computeIfAbsent(b.compositeSlug,
                    slug -> embeddingClient.embed(normalizeTitle(b)));
            return EmbeddingUtils.cosine(first, second);
        } catch (RuntimeException e) {
            System.err.println("Impossibile confrontare i titoli dei moduli: " + e.getMessage());
            return -1.0;
        }
    }

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

    public String clarificationGuidance(List<ScoredCategory> candidates) {
        if (taxonomyBySlug.isEmpty() || candidates == null || candidates.size() < 2) {
            return "";
        }
        Map<String, Set<String>> values = new LinkedHashMap<>();
        values.put("fase", new LinkedHashSet<>());
        values.put("dominio", new LinkedHashSet<>());
        values.put("famiglia", new LinkedHashSet<>());
        for (ScoredCategory candidate : candidates) {
            TaxonomyMetadata metadata = taxonomyBySlug.get(candidate.schema.compositeSlug);
            if (metadata == null) continue;
            addGuidanceValue(values.get("fase"), metadata.lifecycle);
            addGuidanceValue(values.get("dominio"), metadata.domain);
            addGuidanceValue(values.get("famiglia"), metadata.serviceFamily);
        }
        StringBuilder guidance = new StringBuilder();
        for (Map.Entry<String, Set<String>> entry : values.entrySet()) {
            if (entry.getValue().size() > 1) {
                if (guidance.length() > 0) guidance.append("; ");
                guidance.append(entry.getKey()).append(": ")
                        .append(String.join(", ", entry.getValue()));
            }
        }
        return guidance.length() == 0 ? "" :
                "Discriminanti tassonomici osservati: " + guidance + ".";
    }

    private void addGuidanceValue(Set<String> values, String value) {
        if (values.size() < 5 && value != null && !value.trim().isEmpty()) {
            values.add(value.replace('-', ' '));
        }
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
            if (useStopwords && ITALIAN_STOPWORDS.contains(token)) continue;
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
        if (word.length() > 5 && (word.endsWith("ia") || word.endsWith("ie")
                || word.endsWith("io") || word.endsWith("ii"))) {
            return word.substring(0, word.length() - 1);
        }
        char last = word.charAt(word.length() - 1);
        if (last == 'a' || last == 'e' || last == 'i' || last == 'o') {
            return word.substring(0, word.length() - 1);
        }
        return word;
    }
}
