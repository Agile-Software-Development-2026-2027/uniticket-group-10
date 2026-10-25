package it.unical.uniticket.api.dto;

import java.util.ArrayList;
import java.util.List;

public class CatalogExport {
    public String scrapedAt;
    public String baseUrl;
    public List<StructureEntry> structures = new ArrayList<>();
    public List<CategoryFormSchema> allTicketsFlat = new ArrayList<>();
}
