package it.unical.uniticket.api.dto;

import java.util.ArrayList;
import java.util.List;

public class StructureEntry {
    public String structureSlug;
    public String structureName;
    public boolean active;
    public List<CategoryFormSchema> categories = new ArrayList<>();

    public StructureEntry() {
    }

    public StructureEntry(String structureSlug, String structureName) {
        this.structureSlug = structureSlug;
        this.structureName = structureName;
    }
}
