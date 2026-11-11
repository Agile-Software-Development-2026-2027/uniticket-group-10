import { defineToolkit } from "@assistant-ui/react";
import { TicketSuggestions } from "./components/tools/ticket-suggestions";

// Tools execute on the agent; these entries only register their UI.
export const assistantToolkit = defineToolkit({
  suggest_tickets: { type: "backend", render: TicketSuggestions },
});
