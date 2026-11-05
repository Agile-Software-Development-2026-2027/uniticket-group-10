package it.unical.uniticket.dialog;

import static it.unical.uniticket.TestData.CATALOG;
import static it.unical.uniticket.TestData.estimate;
import static it.unical.uniticket.TestData.form;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import it.unical.uniticket.Http;
import it.unical.uniticket.catalog.Category;
import it.unical.uniticket.dialog.Reply.Kind;
import it.unical.uniticket.estimate.Estimate;
import it.unical.uniticket.estimate.Estimator;
import it.unical.uniticket.estimate.Turn;
import it.unical.uniticket.search.LexicalSearch;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;

/** Il dialogo con un modello finto che restituisce stime preparate: si prova solo il codice. */
class ChatBotTest {

    private static final String ESSE3 = "ict/e3-richiesta-assistenza-esse3";
    private static final String DIBEST = "dibest/richiesta-certificato-di-laurea";
    private static final String DIMES = "dimes/richiesta-certificato-di-iscrizionelaureadiploma-supplement";
    /** Un form aperto alla data dello scrape e chiuso il 31/10/2026. */
    private static final String CLA = "cla/parere-certificazioni-internazionali-in-lingua-inglese";
    private static final LexicalSearch SEARCH = new LexicalSearch(CATALOG);
    private static final Clock SCRAPE_DAY = Clock.fixed(CATALOG.fetchedAt(), ZoneOffset.UTC);

    /** Due versioni della stessa pratica, alla pari: il bot deve chiedere. */
    private static final Estimate TIED = estimate(null, 0, 0, DIBEST, 0.5, DIMES, 0.5);

    /** Restituisce le stime in ordine e registra cosa ha ricevuto; con null simula un modello che non risponde. */
    private static final class FakeEstimator implements Estimator {
        private final Deque<Estimate> answers = new ArrayDeque<>();
        final List<List<Turn>> conversations = new ArrayList<>();
        List<Category> lastCandidates;

        FakeEstimator then(Estimate estimate) {
            answers.add(estimate == null ? new Estimate(List.of(), -1, -1, null) : estimate);
            return this;
        }

        @Override
        public Estimate estimate(List<Turn> conversation, List<Category> candidates) {
            conversations.add(List.copyOf(conversation));
            lastCandidates = candidates;
            Estimate next = answers.poll();
            if (next == null || next.noMatch() < 0) {
                throw new Http.ServiceException("modello spento");
            }
            return next;
        }

        @Override
        public String name() {
            return "finto";
        }

        int calls() {
            return conversations.size();
        }

        String lastTranscript() {
            return Turn.transcript(conversations.get(conversations.size() - 1));
        }
    }

    private static ChatBot bot(Estimator estimator) {
        return bot(estimator, SCRAPE_DAY);
    }

    private static ChatBot bot(Estimator estimator, Clock clock) {
        return new ChatBot(CATALOG, SEARCH, estimator, new DecisionPolicy(DecisionPolicy.Params.DEFAULT), clock);
    }

    // ---------------------------------------------------------------- il percorso normale

    @Test
    void unaRichiestaChiaraSiChiudeAlPrimoTurno() {
        Reply reply = bot(new FakeEstimator().then(estimate(null, 0, 0, ESSE3, 1.0)))
                .reply(new ChatSession(), "non riesco ad accedere a Esse3");
        assertEquals(Kind.SELECTED, reply.kind());
        assertEquals(form(ESSE3), reply.options().get(0));
    }

    @Test
    void chiedeIlDipartimentoEPoiAccettaLaSceltaSenzaInterrogareIlModello() {
        FakeEstimator estimator = new FakeEstimator().then(TIED);
        ChatBot bot = bot(estimator);
        ChatSession session = new ChatSession();
        Reply first = bot.reply(session, "mi serve un certificato di laurea");
        assertEquals(Kind.CLARIFY, first.kind());
        Reply second = bot.reply(session, "2");
        assertEquals(Kind.CONFIRMED, second.kind());
        assertEquals(DIMES, second.options().get(0).id());
        assertEquals(1, estimator.calls());
    }

    @Test
    void unaRispostaLiberaTornaAlModelloConTuttoIlDialogo() {
        FakeEstimator estimator = new FakeEstimator().then(TIED).then(estimate("dimes", 0, 0, DIMES, 1.0));
        ChatBot bot = bot(estimator);
        ChatSession session = new ChatSession();
        bot.reply(session, "mi serve un certificato di laurea");

        Reply second = bot.reply(session, "sono di ingegneria informatica");

        assertEquals(Kind.SELECTED, second.kind());
        String transcript = estimator.lastTranscript();
        assertTrue(transcript.contains("Utente: mi serve un certificato di laurea"), transcript);
        assertTrue(transcript.contains("Assistente: A quale corso di studi o dipartimento fai riferimento?"), transcript);
        assertTrue(transcript.contains("Utente: sono di ingegneria informatica"), transcript);
    }

    @Test
    void dopoLeDomandeConsentiteRestanoLeOpzioni() {
        ChatBot bot = bot(new FakeEstimator().then(TIED).then(TIED).then(TIED).then(TIED));
        ChatSession session = new ChatSession();
        assertEquals(Kind.CLARIFY, bot.reply(session, "mi serve un certificato").kind());
        assertEquals(Kind.CLARIFY, bot.reply(session, "di laurea").kind());
        assertEquals(Kind.CLARIFY, bot.reply(session, "per un concorso").kind());
        Reply last = bot.reply(session, "non so cosa aggiungere");
        assertEquals(Kind.SHORTLIST, last.kind());
        assertEquals(2, last.options().size());
        assertEquals(3, session.questionsAsked());
    }

    @Test
    void unRingraziamentoDopoLaSelezioneChiudeSenzaInterrogareIlModello() {
        FakeEstimator estimator = new FakeEstimator().then(estimate(null, 0, 0, ESSE3, 1.0));
        ChatBot bot = bot(estimator);
        ChatSession session = new ChatSession();
        bot.reply(session, "non riesco ad accedere a Esse3");

        Reply reply = bot.reply(session, "ok grazie");

        assertEquals(Kind.CONFIRMED, reply.kind());
        assertEquals(form(ESSE3), reply.options().get(0));
        assertEquals(1, estimator.calls());
    }

    @Test
    void dopoLaConfermaIlMessaggioSuccessivoEUnaRichiestaNuova() {
        FakeEstimator estimator = new FakeEstimator()
                .then(estimate(null, 0, 0, ESSE3, 1.0))
                .then(TIED);
        ChatBot bot = bot(estimator);
        ChatSession session = new ChatSession();
        bot.reply(session, "non riesco ad accedere a Esse3");
        bot.reply(session, "grazie");

        bot.reply(session, "ora mi serve un certificato di laurea");

        String transcript = estimator.lastTranscript();
        assertTrue(transcript.contains("Utente: ora mi serve un certificato di laurea"), transcript);
        assertFalse(transcript.contains("Esse3"), transcript);
    }

    @Test
    void unMessaggioEnormeVieneTroncato() {
        FakeEstimator estimator = new FakeEstimator().then(estimate(null, 0, 1));
        bot(estimator).reply(new ChatSession(), "certificato ".repeat(5_000));
        assertEquals(2000, estimator.conversations.get(0).get(0).text().length());
    }

    // ---------------------------------------------------------------- rifiuti e candidati

    @Test
    void iModuliRifiutatiNonTornanoTraICandidati() {
        FakeEstimator estimator = new FakeEstimator()
                .then(TIED)
                .then(estimate(null, 1.0, 0, DIBEST, 0.0));
        ChatBot bot = bot(estimator);
        ChatSession session = new ChatSession();
        bot.reply(session, "mi serve un certificato di laurea");
        bot.reply(session, "nessuna di queste");
        assertTrue(estimator.lastCandidates.stream().noneMatch(c -> c.id().equals(DIBEST) || c.id().equals(DIMES)));
        assertEquals(Set.of(DIBEST, DIMES), session.rejected());
    }

    @Test
    void ilModelloSaCosaEStatoRifiutato() {
        FakeEstimator estimator = new FakeEstimator()
                .then(estimate(null, 0, 0, ESSE3, 1.0))
                .then(estimate(null, 1.0, 0));
        ChatBot bot = bot(estimator);
        ChatSession session = new ChatSession();
        bot.reply(session, "non riesco ad accedere a Esse3");

        bot.reply(session, "no");

        assertTrue(session.rejected().contains(ESSE3));
        assertFalse(estimator.lastCandidates.contains(form(ESSE3)), "non deve più essere tra i candidati");
        assertTrue(estimator.lastTranscript().contains("Ho proposto il modulo: " + form(ESSE3).name()),
                "ma il modello deve sapere del rifiuto");
    }

    @Test
    void ilModelloVedeAlPiuIlNumeroDiCandidatiIndicato() {
        FakeEstimator estimator = new FakeEstimator().then(estimate(null, 0, 1));
        new ChatBot(CATALOG, SEARCH, estimator, new DecisionPolicy(DecisionPolicy.Params.DEFAULT), SCRAPE_DAY, 5)
                .reply(new ChatSession(), "mi serve un certificato di laurea");
        assertEquals(5, estimator.lastCandidates.size());
    }

    @Test
    void conPochiCandidatiIModuliPropostiRestanoComunque() {
        FakeEstimator estimator = new FakeEstimator().then(TIED).then(TIED);
        ChatBot bot = new ChatBot(CATALOG, SEARCH, estimator, new DecisionPolicy(DecisionPolicy.Params.DEFAULT),
                SCRAPE_DAY, 1);
        ChatSession session = new ChatSession();
        bot.reply(session, "mi serve un certificato di laurea");
        bot.reply(session, "non so di che dipartimento sono");
        assertTrue(estimator.lastCandidates.containsAll(List.of(form(DIBEST), form(DIMES))));
    }

    @Test
    void unFormChiusoNonVieneMaiMostratoAlModello() {
        String query = "parere sulle certificazioni internazionali in lingua inglese";
        FakeEstimator open = new FakeEstimator().then(estimate(null, 0, 1));
        bot(open).reply(new ChatSession(), query);
        assertTrue(open.lastCandidates.contains(form(CLA)), "il giorno dello scrape il form è aperto");

        FakeEstimator closed = new FakeEstimator().then(estimate(null, 0, 1));
        bot(closed, Clock.fixed(Instant.parse("2026-11-02T10:00:00Z"), ZoneOffset.UTC)).reply(new ChatSession(), query);
        assertFalse(closed.lastCandidates.contains(form(CLA)), "dopo il 31/10 il form è chiuso");
    }

    // ---------------------------------------------------------------- i dipartimenti

    @Test
    void laStrutturaDedottaDalModelloNonBasta() {
        // Il modello dice "DIMES" ma l'utente non l'ha nominato: il bot chiede conferma.
        ChatBot bot = bot(new FakeEstimator().then(estimate("dimes", 0, 0, DIMES, 1.0)));
        ChatSession session = new ChatSession();
        assertEquals(Kind.CONFIRM_STRUCTURE, bot.reply(session, "mi serve un certificato di laurea").kind());
        assertEquals(1, session.questionsAsked());
        assertEquals(Kind.CONFIRMED, bot.reply(session, "sì").kind());
    }

    @Test
    void laStrutturaNominataDallUtenteVale() {
        ChatBot bot = bot(new FakeEstimator().then(estimate("dimes", 0, 0, DIMES, 1.0)));
        assertEquals(Kind.SELECTED,
                bot.reply(new ChatSession(), "certificato di laurea, sono di ingegneria informatica").kind());
    }

    @Test
    void laStrutturaNominataNeiTurniPrecedentiVale() {
        ChatBot bot = bot(new FakeEstimator().then(estimate(null, 0, 1)).then(estimate("dimes", 0, 0, DIMES, 1.0)));
        ChatSession session = new ChatSession();
        bot.reply(session, "sono di ingegneria informatica");

        assertEquals(Kind.SELECTED, bot.reply(session, "mi serve un certificato di laurea").kind());
    }

    /** La struttura compare nelle parole del bot: non vuol dire che l'abbia detta l'utente. */
    @Test
    void laStrutturaCitataDalBotNonContaComeDettaDallUtente() {
        ChatBot bot = bot(new FakeEstimator().then(TIED).then(estimate("dimes", 0, 0, DIMES, 1.0)));
        ChatSession session = new ChatSession();
        bot.reply(session, "mi serve un certificato di laurea");

        assertEquals(Kind.CONFIRM_STRUCTURE, bot.reply(session, "quello per la tesi").kind());
    }

    /** "Certo" non è tra le risposte chiuse: senza questa eccezione il bot ripeterebbe la domanda. */
    @Test
    void unAssensoLiberoConfermaIlModuloAppenaProposto() {
        FakeEstimator estimator = new FakeEstimator()
                .then(estimate("dimes", 0, 0, DIMES, 1.0))
                .then(estimate("dimes", 0, 0, DIMES, 1.0));
        ChatBot bot = bot(estimator);
        ChatSession session = new ChatSession();
        assertEquals(Kind.CONFIRM_STRUCTURE, bot.reply(session, "mi serve un certificato di laurea").kind());

        assertEquals(Kind.SELECTED, bot.reply(session, "certo, è quello").kind());
        assertEquals(2, estimator.calls());
    }

    // ---------------------------------------------------------------- nessun modulo, vaghezza, guasti

    @Test
    void senzaUnModuloAdattoLoDiceENonProponeNulla() {
        ChatSession session = new ChatSession();
        Reply reply = bot(new FakeEstimator().then(estimate(null, 1.0, 0))).reply(session, "voglio prenotare un volo");
        assertEquals(Kind.NO_MATCH, reply.kind());
        assertTrue(reply.options().isEmpty());
        assertTrue(session.proposed().isEmpty());
    }

    @Test
    void unMessaggioVagoChiedeDettagliSenzaOpzioni() {
        Reply reply = bot(new FakeEstimator().then(estimate(null, 0, 1))).reply(new ChatSession(), "ho un problema");
        assertEquals(Kind.CLARIFY, reply.kind());
        assertTrue(reply.options().isEmpty());
    }

    @Test
    void seIlModelloNonRispondeMostraIRisultatiDellaRicerca() {
        Reply reply = bot(new FakeEstimator().then(null)).reply(new ChatSession(), "mi serve un certificato di laurea");
        assertEquals(Kind.DEGRADED, reply.kind());
        assertEquals(3, reply.options().size());
    }

    // ---------------------------------------------------------------- la traccia di --debug

    @Test
    void laTracciaSegueIPassiDelTurnoInOrdine() {
        List<String> trace = bot(new FakeEstimator().then(estimate(null, 0, 0, ESSE3, 1.0)))
                .reply(new ChatSession(), "non riesco ad accedere a Esse3").trace();
        String text = String.join("\n", trace);
        int search = text.indexOf("[Ricerca BM25]");
        int model = text.indexOf("[finto, ");
        int check = text.indexOf("[Verifica struttura]");
        int policy = text.indexOf("[DecisionPolicy]");
        assertTrue(search >= 0 && search < model && model < check && check < policy, text);
        assertTrue(text.contains("100%  " + form(ESSE3).name()), text);
        assertTrue(text.endsWith("→ Selected"), text);
    }

    @Test
    void laTracciaDiceSeLaStrutturaDelModelloVieneScartata() {
        String text = String.join("\n", bot(new FakeEstimator().then(estimate("dimes", 0, 0, DIMES, 1.0)))
                .reply(new ChatSession(), "mi serve un certificato di laurea").trace());
        assertTrue(text.contains("[Verifica struttura] riportata: dimes, accettata: null"), text);
        assertTrue(text.endsWith("→ ConfirmStructure"), text);
    }

    @Test
    void unaSceltaDellUtenteNonPassaDaRicercaEModello() {
        ChatBot bot = bot(new FakeEstimator().then(TIED));
        ChatSession session = new ChatSession();
        bot.reply(session, "mi serve un certificato di laurea");

        String text = String.join("\n", bot.reply(session, "2").trace());

        assertTrue(text.startsWith("[UserChoice]"), text);
        assertTrue(text.contains(DIMES), text);
        assertFalse(text.contains("[Ricerca"), text);
    }

    @Test
    void seIlModelloNonRispondeLaTracciaLoDice() {
        String text = String.join("\n", bot(new FakeEstimator().then(null))
                .reply(new ChatSession(), "mi serve un certificato di laurea").trace());
        assertTrue(text.contains("[Modello non disponibile] modello spento"), text);
        assertFalse(text.contains("[DecisionPolicy]"), text);
    }

    // ---------------------------------------------------------------- lo stato nella sessione

    @Test
    void unSoloBotServeDueUtentiSenzaMescolarli() {
        // Lo stato sta nelle sessioni: le due conversazioni si alternano e ognuna resta coerente.
        ChatBot bot = bot(new FakeEstimator().then(TIED).then(TIED));
        ChatSession anna = new ChatSession();
        ChatSession luca = new ChatSession();
        assertEquals(Kind.CLARIFY, bot.reply(anna, "mi serve un certificato di laurea").kind());
        assertEquals(Kind.CLARIFY, bot.reply(luca, "certificato di laurea per favore").kind());

        assertEquals(DIMES, bot.reply(anna, "2").options().get(0).id());
        assertEquals(DIBEST, bot.reply(luca, "1").options().get(0).id());
        assertTrue(anna.conversation().stream().noneMatch(t -> t.text().contains("per favore")));
    }

    @Test
    void resetRicominciaDaCapo() {
        ChatBot bot = bot(new FakeEstimator().then(TIED));
        ChatSession session = new ChatSession();
        bot.reply(session, "mi serve un certificato di laurea");
        session.reset();
        assertTrue(session.conversation().isEmpty());
        assertTrue(session.proposed().isEmpty());
        assertEquals(0, session.questionsAsked());
    }
}
