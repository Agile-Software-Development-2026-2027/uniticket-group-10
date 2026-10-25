package it.unical.uniticket.api.dto;

import java.util.ArrayList;
import java.util.List;

public class FieldSchema {
    public String name;
    public String label;
    public String type;
    public boolean required;
    public boolean askUser = true;
    public boolean autoFillCheckbox;
    public String placeholder;
    public String helpText;
    public List<OptionItem> options = new ArrayList<>();
}
