package it.unical.uniticket.search;

import static it.unical.uniticket.TestData.CATALOG;
import static it.unical.uniticket.TestData.form;
import static org.junit.jupiter.api.Assertions.assertEquals;

import it.unical.uniticket.Http;
import java.util.List;
import org.junit.jupiter.api.Test;

/** La riserva entra solo quando la ricerca principale non risponde, e solo per quella domanda. */
class FallbackSearchTest {

    private static final String ESSE3 = "ict/e3-richiesta-assistenza-esse3";
    private static final String DIBEST = "dibest/richiesta-certificato-di-laurea";

    /** Restituisce sempre lo stesso modulo; spenta, risponde come un Ollama caduto. */
    private static final class FixedSearch implements Search {
        private final String id;
        boolean down;
        int calls;

        FixedSearch(String id) {
            this.id = id;
        }

        @Override
        public List<Hit> search(String query, int limit) {
            calls++;
            if (down) {
                throw new Http.ServiceException("spenta");
            }
            return List.of(new Hit(form(id), 1.0));
        }

        @Override
        public String name() {
            return id;
        }
    }

    @Test
    void usaLaPrincipaleQuandoRisponde() {
        FixedSearch primary = new FixedSearch(ESSE3);
        FixedSearch fallback = new FixedSearch(DIBEST);
        List<Search.Hit> hits = new FallbackSearch(primary, fallback).search("esse3", 10);
        assertEquals(form(ESSE3), hits.get(0).category());
        assertEquals(0, fallback.calls);
    }

    @Test
    void ripiegaSullaRiservaERiprovaLaPrincipaleAllaDomandaDopo() {
        FixedSearch primary = new FixedSearch(ESSE3);
        FallbackSearch search = new FallbackSearch(primary, new FixedSearch(DIBEST));
        primary.down = true;
        assertEquals(form(DIBEST), search.search("esse3", 10).get(0).category());
        primary.down = false;
        assertEquals(form(ESSE3), search.search("esse3", 10).get(0).category());
    }

    @Test
    void conBm25ComeRiservaRispondeComunque() {
        FixedSearch primary = new FixedSearch(DIBEST);
        primary.down = true;
        List<Search.Hit> hits = new FallbackSearch(primary, new LexicalSearch(CATALOG))
                .search("non riesco ad accedere a Esse3", 5);
        assertEquals(5, hits.size());
    }
}
