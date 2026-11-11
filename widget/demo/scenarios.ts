import type { Message } from "@ag-ui/client";

export const demoScenarios = [
  {
    id: "tutto",
    title: "Tutti i contenuti",
    description: "Markdown, ticket, attività dei tool e suggerimenti.",
  },
  { id: "markdown", title: "Markdown", description: "Titoli, elenchi, tabella, citazione e link." },
  {
    id: "ticket",
    title: "Card dei ticket",
    description: "Cinque richieste, altri risultati e apertura del modulo.",
  },
  {
    id: "tool",
    title: "Attività dei tool",
    description: "Nomi e stati tradotti dei tool senza UI dedicata.",
  },
  {
    id: "tool-errore",
    title: "Errore di un tool",
    description: "Un tool non riuscito, distinto dall’errore della conversazione.",
  },
  {
    id: "tool-lento",
    title: "Attività del tool lunga",
    description: "Otto secondi di esecuzione per vedere lo spinner diventare un check.",
  },
  {
    id: "errore",
    title: "Errore di rete",
    description: "La richiesta fallisce; il messaggio successivo funziona.",
  },
  {
    id: "lento",
    title: "Loader e stop",
    description: "Otto secondi di attesa per provare stop e nuova chat.",
  },
  {
    id: "lungo",
    title: "Conversazione lunga",
    description: "Contenuti estesi per provare scorrimento e ritorno in fondo.",
  },
] as const;

export const markdown = `## Come possiamo aiutarti
Questa è una **risposta simulata**, con *corsivo* e un [link di esempio](https://example.com).

- Certificati e documenti
- Tasse e pagamenti
- Assistenza ai servizi

1. Scegli la richiesta.
2. Controlla i dati.
3. Compila il modulo.

> Nessun dato di questa demo viene inviato a Django o a un modello.

| Richiesta | Ufficio |
| --- | --- |
| Certificato | Segreteria studenti |
| Pagamenti | Ufficio tasse |`;

function wait(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const abort = () => {
      clearTimeout(timer);
      reject(new Error("Demo interrupted"));
    };
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", abort);
      resolve();
    }, ms);
    if (signal.aborted) abort();
    else signal.addEventListener("abort", abort, { once: true });
  });
}

const message = (content: string, id: string = crypto.randomUUID()): Message => ({
  role: "assistant",
  id,
  content,
});
function tool(name: string, content: unknown, failed = false): Message[] {
  const id = crypto.randomUUID();
  return [
    {
      role: "assistant",
      id: crypto.randomUUID(),
      content: "",
      toolCalls: [{ id, type: "function", function: { name, arguments: "{}" } }],
    },
    {
      role: "tool",
      id: crypto.randomUUID(),
      toolCallId: id,
      content: JSON.stringify(content),
      ...(failed ? { error: "DEMO_CATALOG_UNAVAILABLE" } : {}),
    },
  ];
}
function tickets() {
  const titles = [
    "Certificato di iscrizione",
    "Certificato degli esami",
    "Informazioni sulle tasse",
    "Accesso ai servizi informatici",
    "Prenotazione impianti sportivi",
  ];
  return tool("suggest_tickets", {
    message: "Ecco alcune richieste di esempio. Apri una card per provare il modulo.",
    tickets: titles.map((title, index) => ({
      category_id: index + 1,
      title,
      structure_name: [
        "Segreteria studenti",
        "Segreteria studenti",
        "Ufficio tasse",
        "Servizi informatici",
        "Centro sportivo",
      ][index],
      url: `/demo-ticket/${index + 1}/`,
    })),
  });
}

export async function respondToDemo(
  input: { messages?: Message[]; [key: string]: unknown },
  signal: AbortSignal,
  emit?: (messages: Message[]) => void,
) {
  const text = String(input.messages?.at(-1)?.content ?? "");
  const command = text.trim().toLowerCase().replace(/^\//, "");
  await wait(command === "lento" ? 8000 : 200, signal);
  if (command === "errore") throw new Error("DEMO_SIMULATED_FAILURE");
  if (command === "tool-lento") {
    const messages = tool("get_categories", [{ id: 1, title: "Certificato" }]);
    emit?.(messages.slice(0, 1));
    await wait(8000, signal);
    return { messages: [...messages, message("Ricerca delle richieste completata.")] };
  }
  if (command === "ticket")
    return { messages: tickets(), suggestions: ["Quali documenti servono?"] };
  const defaultText =
    "Descrivi ciò di cui hai bisogno oppure scegli uno scenario nella pagina di prova.";
  const prose =
    command === "tutto" || command === "markdown"
      ? markdown
      : command === "lungo"
        ? Array.from(
            { length: 10 },
            (_, i) =>
              `### Passaggio ${i + 1}\nControlla i dati del modulo e prepara la documentazione necessaria.\n\n- Documento di identità\n- Informazioni sulla richiesta\n`,
          ).join("\n")
        : command === "tool"
          ? "Ho consultato gli uffici e le richieste di esempio."
          : command === "tool-errore"
            ? "Il catalogo simulato non è disponibile."
            : command === "lento"
              ? "Attesa completata. Puoi inviare un nuovo messaggio."
              : defaultText;
  const id = crypto.randomUUID();
  // Progressive message events travel through the AG-UI client’s real SSE decoder.
  for (let end = 70; end < prose.length; end += 70) {
    emit?.([message(prose.slice(0, end), id)]);
    await wait(25, signal);
  }
  const messages: Message[] = [message(prose, id)];
  if (command === "tutto") messages.push(...tickets());
  if (command === "tutto" || command === "tool")
    messages.push(
      ...tool("get_structures", [{ id: 1, name: "Segreteria studenti" }]),
      ...tool("get_categories", [{ id: 1, title: "Certificato" }]),
    );
  if (command === "tutto" || command === "tool-errore")
    messages.push(...tool("get_categories", { error: "DEMO_CATALOG_UNAVAILABLE" }, true));
  return { messages, suggestions: ["Quali documenti servono?", "Come compilo questo modulo?"] };
}
