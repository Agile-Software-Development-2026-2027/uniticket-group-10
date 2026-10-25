package it.unical.uniticket.api.dto;

import java.util.ArrayList;
import java.util.List;

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
    public List<FieldSchema> fields = new ArrayList<>();
}
