package it.unical.uniticket.api.dto;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public class CategoryFormSchema {
    public String compositeSlug;
    public String structureSlug;
    public String structureName;
    public String categorySlug;
    public String categoryTitle;
    public String url;
    public boolean accessible;
    public String accessRestrictionReason;
    public String categoryNotes;
    public String schemaHash;
    public String jevCriterionSummary;
    public String ragSearchText;
    public JsonNode availability;
    public JsonNode routerCard;
    public JsonNode fields;
}
