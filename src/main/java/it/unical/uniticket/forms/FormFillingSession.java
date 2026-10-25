package it.unical.uniticket.forms;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import it.unical.uniticket.api.dto.CategoryFormSchema;
import it.unical.uniticket.api.dto.FieldSchema;
import it.unical.uniticket.api.dto.OptionItem;
import it.unical.uniticket.llm.LlmClient;
import it.unical.uniticket.rag.OptionEmbeddingIndex;
import it.unical.uniticket.rag.OptionEmbeddingIndex.OptionMatch;

import java.io.File;
import java.io.IOException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * Gestisce la raccolta e la validazione dei dati di un modulo già classificato.
 *
 * <p>Questa classe è separata dal routing: la classificazione può quindi essere
 * usata senza inizializzare o importare la logica di compilazione dei form.</p>
 */
public class FormFillingSession {
    private static final int OPTION_LIST_MAX_IN_PROMPT = 8;
    private static final int OPTION_CANDIDATES_FOR_LLM = 5;
    private static final double OPTION_EMBED_DIRECT_THRESHOLD = 0.85;

    private final CategoryFormSchema schema;
    private final LlmClient llmClient;
    private final OptionEmbeddingIndex optionIndex;
    private final ObjectMapper mapper = new ObjectMapper();
    private final Map<String, String> collectedTextData = new LinkedHashMap<>();
    private final Map<String, File> collectedFiles = new LinkedHashMap<>();
    private final List<String> conversationHistory = new ArrayList<>();

    public FormFillingSession(CategoryFormSchema schema, LlmClient llmClient,
                              OptionEmbeddingIndex optionIndex) {
        this.schema = schema;
        this.llmClient = llmClient;
        this.optionIndex = optionIndex;
        for (FieldSchema field : schema.fields) {
            if (field.autoFillCheckbox) {
                collectedTextData.put(field.name, "on");
            }
        }
    }

    public CategoryFormSchema getSchema() {
        return schema;
    }

    public Map<String, String> getCollectedTextData() {
        return Collections.unmodifiableMap(collectedTextData);
    }

    public Map<String, File> getCollectedFiles() {
        return Collections.unmodifiableMap(collectedFiles);
    }

    public List<FieldSchema> getMissingRequiredFields() {
        return schema.fields.stream()
                .filter(field -> field.askUser && field.required)
                .filter(field -> "file".equalsIgnoreCase(field.type)
                        ? !collectedFiles.containsKey(field.name)
                        : isBlank(collectedTextData.get(field.name)))
                .collect(Collectors.toList());
    }

    public boolean isReadyToSubmit() {
        return schema.accessible && getMissingRequiredFields().isEmpty();
    }

    public String processUserMessage(String userMessage) {
        if (!schema.accessible) {
            return "Il modulo \"" + schema.categoryTitle + "\" non è attualmente accessibile.";
        }
        conversationHistory.add("Utente: " + userMessage);
        extractFields(userMessage);
        List<FieldSchema> missing = getMissingRequiredFields();
        return missing.isEmpty() ? buildConfirmationSummary() : buildNextQuestionPrompt(missing);
    }

    public void attachFile(String fieldName, File file) {
        if (file != null && file.isFile()) {
            collectedFiles.put(fieldName, file);
        }
    }

    private void extractFields(String latestMessage) {
        StringBuilder fields = new StringBuilder();
        for (FieldSchema field : schema.fields) {
            if (!field.askUser) continue;
            fields.append("- name: \"").append(field.name).append("\" | label: \"")
                    .append(field.label).append("\" | type: ").append(field.type)
                    .append(" | required: ").append(field.required).append("\n");
            if (field.helpText != null && !field.helpText.isEmpty()) {
                fields.append("  help: \"").append(field.helpText).append("\"\n");
            }
            if (!field.options.isEmpty() && field.options.size() <= OPTION_LIST_MAX_IN_PROMPT) {
                fields.append("  valori ammessi: ")
                        .append(field.options.stream().map(option -> option.value)
                                .collect(Collectors.joining(", "))).append("\n");
            }
        }
        String systemPrompt = "Estrai i valori esplicitamente forniti dall'utente per compilare il modulo \""
                + schema.categoryTitle + "\". Non inventare dati. Rispondi solo con JSON piatto.";
        String userPrompt = "CAMPI:\n" + fields + "\nDATI RACCOLTI:\n" + collectedTextData
                + "\nCONVERSAZIONE:\n" + conversationHistory + "\nULTIMO MESSAGGIO:\n" + latestMessage;
        try {
            JsonNode extracted = parseJson(llmClient.generate(systemPrompt, userPrompt));
            List<FieldSchema> ambiguousFields = new ArrayList<>();
            List<String> ambiguousValues = new ArrayList<>();
            for (FieldSchema field : schema.fields) {
                if (!field.askUser || !extracted.has(field.name)) continue;
                String value = extracted.path(field.name).asText("").trim();
                if (!value.isEmpty()) validateAndStore(field, value, ambiguousFields, ambiguousValues);
            }
            resolveAmbiguousFields(ambiguousFields, ambiguousValues);
        } catch (Exception ignored) {
            // I dati già raccolti restano validi; i campi mancanti verranno richiesti di nuovo.
        }
    }

    private void validateAndStore(FieldSchema field, String value,
                                  List<FieldSchema> ambiguous, List<String> rawValues) {
        if ("file".equalsIgnoreCase(field.type)) {
            File file = new File(value);
            if (file.isFile()) collectedFiles.put(field.name, file);
            return;
        }
        for (OptionItem option : field.options) {
            if (equals(option.value, value) || equals(option.label, value)) {
                collectedTextData.put(field.name, option.value);
                return;
            }
        }
        if (field.options.isEmpty()) {
            collectedTextData.put(field.name, value);
            return;
        }
        if (optionIndex != null) {
            List<OptionMatch> matches = optionIndex.findTopCandidates(value, schema, field, 1);
            if (!matches.isEmpty() && matches.get(0).score >= OPTION_EMBED_DIRECT_THRESHOLD) {
                collectedTextData.put(field.name, matches.get(0).option.value);
                return;
            }
        }
        ambiguous.add(field);
        rawValues.add(value);
    }

    private void resolveAmbiguousFields(List<FieldSchema> fields, List<String> values) {
        if (fields.isEmpty() || optionIndex == null) return;
        StringBuilder prompt = new StringBuilder("Scegli tra i candidati. Usa NONE se nessuno è corretto.\n");
        for (int i = 0; i < fields.size(); i++) {
            FieldSchema field = fields.get(i);
            prompt.append("\nCAMPO ").append(field.name).append(": ").append(values.get(i)).append("\n");
            for (OptionItem option : optionIndex.findTopCandidates(values.get(i), schema, field,
                    OPTION_CANDIDATES_FOR_LLM).stream().map(match -> match.option)
                    .collect(Collectors.toList())) {
                prompt.append("- ").append(option.value).append("\n");
            }
        }
        try {
            JsonNode result = parseJson(llmClient.generate(
                    "Sei un assistente che seleziona opzioni di un modulo.", prompt.toString()));
            for (FieldSchema field : fields) {
                String chosen = result.path(field.name).asText("").trim();
                for (OptionItem option : field.options) {
                    if (equals(option.value, chosen) || equals(option.label, chosen)) {
                        collectedTextData.put(field.name, option.value);
                        break;
                    }
                }
            }
        } catch (Exception ignored) {
            // Il campo resta mancante e verrà richiesto nel turno successivo.
        }
    }

    private String buildNextQuestionPrompt(List<FieldSchema> missing) {
        StringBuilder result = new StringBuilder("Per completare la richiesta servono ancora:\n");
        for (int i = 0; i < Math.min(3, missing.size()); i++) {
            FieldSchema field = missing.get(i);
            result.append(i + 1).append(". ").append(field.label);
            if (!field.options.isEmpty()) {
                result.append(" (opzioni: ").append(field.options.stream().limit(10)
                        .map(option -> option.label).collect(Collectors.joining(", "))).append(")");
            }
            result.append("\n");
        }
        return result.toString();
    }

    private String buildConfirmationSummary() {
        StringBuilder result = new StringBuilder("Tutti i campi obbligatori sono stati compilati:\n");
        collectedTextData.forEach((key, value) -> result.append("- ").append(key).append(": ")
                .append(value).append("\n"));
        collectedFiles.forEach((key, value) -> result.append("- ").append(key).append(": ")
                .append(value.getName()).append("\n"));
        return result.toString();
    }

    private JsonNode parseJson(String raw) throws IOException {
        if (raw == null) throw new IOException("Risposta LLM vuota.");
        int first = raw.indexOf('{');
        int last = raw.lastIndexOf('}');
        if (first < 0 || last <= first) throw new IOException("Risposta LLM non JSON.");
        return mapper.readTree(raw.substring(first, last + 1));
    }

    private boolean equals(String first, String second) {
        return first != null && second != null && first.equalsIgnoreCase(second);
    }

    private boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }
}
