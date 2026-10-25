package it.unical.uniticket.api.dto;

import com.fasterxml.jackson.databind.JsonNode;

public class TicketResult {
    public final boolean success;
    public final String ticketUrl;
    public final String message;
    public final JsonNode responseJson;

    public TicketResult(boolean success, String ticketUrl, String message, JsonNode responseJson) {
        this.success = success;
        this.ticketUrl = ticketUrl;
        this.message = message;
        this.responseJson = responseJson;
    }
}
