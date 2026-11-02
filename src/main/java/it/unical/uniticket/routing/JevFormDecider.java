package it.unical.uniticket.routing;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import it.unical.uniticket.access.UserProfile;
import it.unical.uniticket.llm.JevClient;
import it.unical.uniticket.rag.UniTicketRagEngine.ScoredCategory;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;

/**
 * Decisore basato su Jev. Ogni chiamata contiene una scelta tra i candidati, che li confronta,
 * e una domanda sì/no per candidato, che lo giudica da solo. Servono entrambe: le probabilità di
 * una scelta sommano a 1 tra le opzioni offerte, quindi dicono quale candidato è il migliore ma
 * non se ne va bene almeno uno. Con un solo candidato la scelta vale sempre 1.
 *
 * <p>La {@code confidence} del verdetto è una probabilità, come chiede {@link RoutingPolicy}. Il
 * campo {@code confidence} di Jev non lo è: misura quanto la distribuzione è concentrata e cambia
 * con il numero di opzioni, quindi non viene letto.</p>
 *
 * <p>Domande e soglie stanno tutte qui. Le domande sono in inglese, la lingua in cui Jev è più
 * accurato; richiesta e moduli restano in italiano. Lingua e soglie non sono state misurate su
 * questo catalogo.</p>
 */
public class JevFormDecider implements FormDecider {
    static final String CHOICE_QUESTION = "modulo";
    static final String FIT_QUESTION_PREFIX = "pertinenza_";

    private static final String CHOICE_INSTRUCTIONS =
            "Which of these uniTicket forms of the University of Calabria does the user need for "
            + "`request`? Users write in their own words: judge the need, not the words shared "
            + "with a title. `user_profile`, if present, is only a hint: a structure named in "
            + "`request` prevails.";
    private static final String FIT_INSTRUCTIONS =
            "Does this uniTicket form handle what the user needs in `request`?";
    private static final String FIT_TRUE =
            "The form deals with the user's need, even if the user describes it in other words.";
    private static final String FIT_FALSE =
            "The form deals with something else and shares at most generic words such as "
            + "problema, assistenza, richiesta or iscrizione.";

    /** Se nessun candidato arriva a questa pertinenza, nessuno è adatto: è il "no" suggerito da TypeSafe. */
    static final double MIN_FIT = 0.30;
    /**
     * Un candidato è un'alternativa se la sua probabilità arriva a questa frazione di quella del
     * migliore. Con 0.5 può accadere solo se il migliore non supera 2/3, quindi sotto
     * {@link RoutingPolicy#SELECT_MIN_CONFIDENCE}: decide quali opzioni mostrare, non se selezionare.
     */
    static final double ALTERNATIVE_MIN_RATIO = 0.5;

    private final JevClient client;
    private final ObjectMapper mapper = new ObjectMapper();

    public JevFormDecider(JevClient client) {
        this.client = client;
    }

    @Override
    public String name() {
        return "Jev (" + client.modelName() + ")";
    }

    @Override
    public DeciderVerdict decide(String request, List<ScoredCategory> candidates, UserProfile profile) {
        try {
            JsonNode answers = client.ask(buildState(request, profile), buildQuestions(candidates));
            return toVerdict(answers, candidates.size());
        } catch (RuntimeException e) {
            return DeciderVerdict.failed("Risposta di Jev non utilizzabile: " + e.getMessage());
        }
    }

    private ObjectNode buildState(String request, UserProfile profile) {
        ObjectNode state = mapper.createObjectNode();
        state.put("request", request);
        String profileText = LlmFormDecider.describeProfile(profile);
        if (!profileText.isEmpty()) state.put("user_profile", profileText);
        return state;
    }

    /** I candidati usano il testo di {@link LlmFormDecider}: tra i due decisori cambia solo il modello. */
    private ObjectNode buildQuestions(List<ScoredCategory> candidates) {
        ObjectNode questions = mapper.createObjectNode();
        ObjectNode choice = questions.putObject(CHOICE_QUESTION);
        choice.put("type", "choice");
        choice.put("instructions", CHOICE_INSTRUCTIONS);
        ObjectNode options = choice.putObject("criteria");
        for (int i = 0; i < candidates.size(); i++) {
            String description = LlmFormDecider.describe(candidates.get(i));
            options.put(option(i), description);
            questions.set(FIT_QUESTION_PREFIX + option(i), buildFitQuestion(description));
        }
        return questions;
    }

    private ObjectNode buildFitQuestion(String description) {
        ObjectNode question = mapper.createObjectNode();
        question.put("type", "noul");
        ObjectNode instructions = question.putObject("instructions");
        instructions.put("question", FIT_INSTRUCTIONS);
        instructions.put("form", description);
        ObjectNode criteria = question.putObject("criteria");
        criteria.put("true", FIT_TRUE);
        criteria.put("false", FIT_FALSE);
        return question;
    }

    private DeciderVerdict toVerdict(JsonNode answers, int candidateCount) {
        JsonNode choice = answers.path(CHOICE_QUESTION);
        String chosen = choice.path("choice").asText();
        double[] probabilities = new double[candidateCount];
        double[] fits = new double[candidateCount];
        int best = DeciderVerdict.NO_MATCH;
        for (int i = 0; i < candidateCount; i++) {
            probabilities[i] = probability(choice.path("probabilities").path(option(i)));
            fits[i] = probability(answers.path(FIT_QUESTION_PREFIX + option(i)).path("noul"));
            if (option(i).equals(chosen)) best = i;
        }
        if (best == DeciderVerdict.NO_MATCH) {
            throw new IllegalStateException("opzione non offerta: " + chosen);
        }

        double topFit = Arrays.stream(fits).max().orElse(0.0);
        if (topFit < MIN_FIT) {
            return DeciderVerdict.noMatch(String.format(Locale.ROOT, "Jev: pertinenza massima %.2f.", topFit));
        }

        List<Integer> alternatives = new ArrayList<>();
        for (int i = 0; i < candidateCount; i++) {
            if (i != best && probabilities[i] >= ALTERNATIVE_MIN_RATIO * probabilities[best]) {
                alternatives.add(i);
            }
        }
        alternatives.sort(Comparator.comparingDouble(index -> -probabilities[index]));

        // Il modulo giusto deve battere gli altri candidati ed essere adatto di per sé.
        double confidence = Math.min(probabilities[best], fits[best]);
        return DeciderVerdict.match(best, alternatives, confidence, String.format(Locale.ROOT,
                "Jev: probabilità %.2f, pertinenza %.2f.", probabilities[best], fits[best]), "");
    }

    private double probability(JsonNode value) {
        if (!value.isNumber() || value.asDouble() < 0.0 || value.asDouble() > 1.0) {
            throw new IllegalStateException("probabilità assente o non valida: " + value);
        }
        return value.asDouble();
    }

    /** I nomi delle opzioni vengono letti dal modello: i numeri non favoriscono nessun candidato. */
    private String option(int index) {
        return String.valueOf(index + 1);
    }
}
