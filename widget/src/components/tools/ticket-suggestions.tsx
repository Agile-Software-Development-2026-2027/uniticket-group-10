import type { ToolCallMessagePartComponent } from "@assistant-ui/react";
import { z } from "zod";
import { TicketResults } from "../ticket/ticket-results";
import { ToolFallback } from "./tool-fallback";

const ticketResultSchema = z.object({
  message: z.string().optional(),
  tickets: z.array(
    z.object({
      category_id: z.number().int().positive(),
      title: z.string(),
      structure_name: z.string(),
      url: z.string().refine(
        (url) =>
          url.startsWith("/") &&
          !url.startsWith("//") &&
          // oxlint-disable-next-line no-control-regex -- Reject control characters in agent-provided URLs.
          !/[\\\u0000-\u0020\u007f]/.test(url),
        "Expected a same-origin path",
      ),
    }),
  ),
});

// https://www.assistant-ui.com/docs/runtimes/langgraph/tutorial/part-2
// https://www.assistant-ui.com/docs/tools/tool-ui
/** Valida il risultato di suggest_tickets e mostra le card oppure il fallback del tool. */
export const TicketSuggestions: ToolCallMessagePartComponent = (props) => {
  const result = readTicketResult(props.result);
  return result && !props.isError ? (
    <>
      {result.message && <p className="assistant-markdown">{result.message}</p>}
      <TicketResults tickets={result.tickets} />
    </>
  ) : (
    <ToolFallback {...props} />
  );
};

export function readTicketResult(value: unknown): z.infer<typeof ticketResultSchema> | null {
  if (typeof value === "string") {
    try {
      value = JSON.parse(value);
    } catch {
      return null;
    }
  }
  const result = ticketResultSchema.safeParse(value);
  return result.success ? result.data : null;
}
