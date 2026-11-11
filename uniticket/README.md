# TicketCategory — ricezione e orchestratore

Documentazione unica: [flusso attuale, prove e prossimi passi](docs/FLUSSO_TICKET_CATEGORY.md).

CREATE/UPDATE chiamano il provider del modello di embedding; DELETE usa solo l’ID. Il repository non è ancora collegato. La generazione reale richiede il servizio Ollama disponibile; i test simulano la risposta HTTP.
