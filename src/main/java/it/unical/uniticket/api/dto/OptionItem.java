package it.unical.uniticket.api.dto;

public class OptionItem {
    public String value;
    public String label;

    public OptionItem() {
    }

    public OptionItem(String value, String label) {
        this.value = value;
        this.label = label;
    }
}
