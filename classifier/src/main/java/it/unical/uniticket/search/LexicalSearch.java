package it.unical.uniticket.search;

import it.unical.uniticket.catalog.Catalog;
import it.unical.uniticket.catalog.Category;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.apache.lucene.analysis.Analyzer;
import org.apache.lucene.analysis.it.ItalianAnalyzer;
import org.apache.lucene.document.Document;
import org.apache.lucene.document.Field;
import org.apache.lucene.document.StoredField;
import org.apache.lucene.document.TextField;
import org.apache.lucene.index.DirectoryReader;
import org.apache.lucene.index.IndexWriter;
import org.apache.lucene.index.IndexWriterConfig;
import org.apache.lucene.search.BooleanClause.Occur;
import org.apache.lucene.search.BooleanQuery;
import org.apache.lucene.search.BoostQuery;
import org.apache.lucene.search.IndexSearcher;
import org.apache.lucene.search.Query;
import org.apache.lucene.search.ScoreDoc;
import org.apache.lucene.store.ByteBuffersDirectory;
import org.apache.lucene.util.QueryBuilder;

/**
 * BM25 in memoria con l'analizzatore italiano di Lucene (stemming, stopword, elisioni).
 * Il titolo pesa più del resto: è il testo più curato, mentre campi e avvisi spesso parlano d'altro.
 */
public final class LexicalSearch implements Search {

    private static final Map<String, Float> FIELD_WEIGHTS = Map.of(
            "title", 3f, "summary", 1.5f, "structure", 1f, "detail", 0.5f);

    private final Catalog catalog;
    private final Analyzer analyzer = new ItalianAnalyzer();
    private final IndexSearcher searcher;

    public LexicalSearch(Catalog catalog) {
        this.catalog = catalog;
        ByteBuffersDirectory directory = new ByteBuffersDirectory();
        try (IndexWriter writer = new IndexWriter(directory, new IndexWriterConfig(analyzer))) {
            for (Category category : catalog.categories()) {
                Document doc = new Document();
                doc.add(new StoredField("id", category.id()));
                doc.add(new TextField("title", category.name(), Field.Store.NO));
                doc.add(new TextField("summary", category.summary(), Field.Store.NO));
                doc.add(new TextField("structure", catalog.structureText(category), Field.Store.NO));
                doc.add(new TextField("detail", catalog.searchDetail(category), Field.Store.NO));
                writer.addDocument(doc);
            }
            writer.commit();
            searcher = new IndexSearcher(DirectoryReader.open(directory));
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    @Override
    public List<Hit> search(String query, int limit) {
        BooleanQuery.Builder combined = new BooleanQuery.Builder();
        boolean any = false;
        for (Map.Entry<String, Float> field : FIELD_WEIGHTS.entrySet()) {
            Query clause = new QueryBuilder(analyzer).createBooleanQuery(field.getKey(), query, Occur.SHOULD);
            if (clause != null) {
                combined.add(new BoostQuery(clause, field.getValue()), Occur.SHOULD);
                any = true;
            }
        }
        List<Hit> hits = new ArrayList<>();
        if (!any) {
            return hits; // solo stopword o punteggiatura
        }
        try {
            for (ScoreDoc doc : searcher.search(combined.build(), limit).scoreDocs) {
                String id = searcher.storedFields().document(doc.doc).get("id");
                hits.add(new Hit(catalog.byId(id).orElseThrow(), doc.score));
            }
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
        return hits;
    }

    @Override
    public String name() {
        return "BM25";
    }
}
