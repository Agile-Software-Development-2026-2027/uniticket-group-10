import { EventEncoder } from "@ag-ui/encoder";
import { EventType, type Message, type RunAgentInput } from "@ag-ui/client";

type DemoClient = (
  input: { messages?: Message[]; [key: string]: unknown },
  signal: AbortSignal,
  emit?: (messages: Message[]) => void,
) => Promise<{
  messages: Message[];
  suggestions?: (string | { prompt: string; title?: string })[];
}>;

/** Serve soltanto demo e test; gli eventi usano l'encoder ufficiale AG-UI. */
export function createAgUiFixture(client: DemoClient): typeof fetch {
  return async (_request, init) => {
    const url = new URL(
      _request instanceof Request ? _request.url : String(_request),
      "http://localhost",
    );
    if (url.pathname === "/api/assistant/thread/new/" && init?.method === "POST") {
      return Response.json({ thread_id: crypto.randomUUID() }, { status: 201 });
    }
    const input = JSON.parse(String(init?.body)) as RunAgentInput;
    if (!input.threadId || !input.runId) throw new Error("Unexpected fixture endpoint");
    const encoder = new EventEncoder();
    const bytes = new TextEncoder();
    const signal = init?.signal ?? new AbortController().signal;
    let closed = false;
    return new Response(
      new ReadableStream<Uint8Array>({
        start(controller) {
          const emit = (event: Parameters<EventEncoder["encode"]>[0]) => {
            if (!closed) controller.enqueue(bytes.encode(encoder.encode(event)));
          };
          const streamed = new Map<string, string>();
          const streamedTools = new Set<string>();
          const progress = (messages: Message[], streamTools = true) => {
            for (const message of messages) {
              if (message.role !== "assistant") continue;
              for (const call of streamTools ? (message.toolCalls ?? []) : []) {
                if (streamedTools.has(call.id)) continue;
                emit({
                  type: EventType.TOOL_CALL_START,
                  toolCallId: call.id,
                  toolCallName: call.function.name,
                  parentMessageId: message.id,
                });
                emit({
                  type: EventType.TOOL_CALL_ARGS,
                  toolCallId: call.id,
                  delta: call.function.arguments,
                });
                emit({ type: EventType.TOOL_CALL_END, toolCallId: call.id });
                streamedTools.add(call.id);
              }
              if (typeof message.content !== "string" || !message.content) continue;
              if (!streamed.has(message.id))
                emit({
                  type: EventType.TEXT_MESSAGE_START,
                  messageId: message.id,
                  role: "assistant",
                });
              const before = streamed.get(message.id) ?? "";
              const delta = message.content.slice(before.length);
              if (delta)
                emit({ type: EventType.TEXT_MESSAGE_CONTENT, messageId: message.id, delta });
              streamed.set(message.id, message.content);
            }
          };
          emit({ type: EventType.RUN_STARTED, threadId: input.threadId, runId: input.runId });
          void client({ messages: input.messages }, signal, progress)
            .then((response) => {
              if (closed || signal.aborted) return;
              progress(response.messages, false);
              for (const messageId of streamed.keys())
                emit({ type: EventType.TEXT_MESSAGE_END, messageId });
              emit({
                type: EventType.MESSAGES_SNAPSHOT,
                messages: [...input.messages, ...response.messages],
              });
              emit({
                type: EventType.STATE_SNAPSHOT,
                snapshot: { suggestions: response.suggestions ?? [] },
              });
              emit({ type: EventType.RUN_FINISHED, threadId: input.threadId, runId: input.runId });
            })
            .catch(() => {
              if (!signal.aborted)
                emit({ type: EventType.RUN_ERROR, message: "Demo request failed" });
            })
            .finally(() => {
              if (!closed) {
                closed = true;
                controller.close();
              }
            });
          signal.addEventListener(
            "abort",
            () => {
              if (!closed) {
                closed = true;
                controller.close();
              }
            },
            { once: true },
          );
        },
        cancel() {
          closed = true;
        },
      }),
      { headers: { "Content-Type": encoder.getContentType() } },
    );
  };
}
