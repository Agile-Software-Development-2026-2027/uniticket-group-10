# Widget assistente UniTicket

Assistant-ui offre degli adapter per usare ag-ui (`@assistant-ui/react-ag-ui`) senza fare accrocchi strani.
Ho fatto delle prove pure con l'adapter diretto a LangGraph ma è un macello, bisogna esporre almeno 5 endpoint inutilmente...

Il flusso è **widget → Django → agente**.
Thread, messaggi, stream, stop e rigenerazione sono gestiti dall’adapter.

## TODO
- Integrare le suggestions (quick replies), ho evitato di farlo ora perché bisogna capire meglio come farlo.

## Come aggiungere un renderer personalizzato a un tool
Il tool viene eseguito dall’agente LangGraph; il widget ne visualizza la chiamata
con un componente React. Per aggiungere una UI dedicata, crea il renderer,
registralo con il nome esatto del tool e aggiungi le traduzioni della sua etichetta.

Se non ti serve un renderer personalizzato, ma hai definito un tool basta
[aggiungere l’etichetta in italiano e inglese](#3-aggiungere-letichetta-in-italiano-e-inglese).
Senza traduzione, il tool viene mostrato con il testo generico “Attività dell’assistente”
o “Assistant activity”, in base alla lingua del widget.

### 1. Creare il componente

Crea un componente di tipo `ToolCallMessagePartComponent` in
`src/components/tools/`. Riceve gli argomenti (`args`), il risultato (`result`)
e lo stato della chiamata (`status`, `isError`). Durante lo streaming il risultato
può non essere ancora disponibile.

Un'esempio è [`ticket-suggestions.tsx`](src/components/tools/ticket-suggestions.tsx):


### 2. Registrare il renderer
Importa il componente in [`src/tools.tsx`](src/tools.tsx) e aggiungilo al toolkit:

```tsx
export const assistantToolkit = defineToolkit({
  spritz_tool: { type: "backend", render: TicketSuggestions },
});
```

La chiave `spritz_tool` deve coincidere esattamente con il nome del tool
LangGraph. `type: "backend"` indica che il tool viene eseguito sul server.
I tool senza un renderer registrato vengono mostrati con `ToolFallback`.

### 3. Aggiungere l’etichetta in italiano e inglese

Aggiungi la chiave `tool.<nome_del_tool>` agli oggetti JSON esistenti, mantenendo
le altre traduzioni. Per esempio, in [`src/i18n/it.json`](src/i18n/it.json):

```json
{
  "tool.spritz_tool": "Preparando uno spritz"
}
```

E in [`src/i18n/en.json`](src/i18n/en.json):

```json
{
  "tool.suggest_tickets": "Preparing a spritz"
}
```

Se non applichi questa etichetta verrà usata quella di default.
```

## Sviluppo e verifica

```sh
npm ci
npm run dev
npm test
npm run lint
npm run build
```

Se vuoi migliorare l'interfaccia grafica, installa le dipendeze e fai `npm run dev`, avrai una pagina demo che simula alcuni comportamenti del widget.

## Struttura

```text
src/
  assistant.tsx       # Provider e adapter AG-UI
  embed.tsx           # Montaggio nella pagina Django
  tools.tsx           # Registro dei renderer dei tool
  components/        # Pannello, thread, messaggi, composer e Markdown
    tools/           # Fallback e renderer dei suggerimenti dei ticket
    ticket/          # Card e lista dei ticket
  django/            # Sessione, CSRF e integrazione dei moduli HTMX
  hooks/             # Ridimensionamento del pannello
  i18n/              # Traduzioni IT/EN, incluse le etichette tool.<nome>
  styles/            # CSS del widget
demo/               # Pagina di prova, scenari e backend simulato, esclusi dal widget
scripts/build.mjs    # Build del widget e build separata della demo
tests/              # Verifiche del widget, della demo e della separazione delle build
```

## Incorporamento in Django

```django
{% load static %}
<link rel="stylesheet" href="{% static 'chat/vendor/assistant-ui.css' %}">
<div id="assistant-widget" data-language="it"
     data-agui-url="/api/assistant">
  <div hidden>{% csrf_token %}</div>
</div>
<script src="{% static 'chat/vendor/assistant-ui.js' %}" defer></script>
```

Il bundle monta automaticamente il widget.

HTMX è fornito dalla pagina Django (stiamo dando per scontato che non lo toglieranno). Le card aggiornano `#assistant-page-content` e mantengono `#assistant-root` come target di sincronizzazione. Il widget deve restare fuori dal contenuto sostituito.

La selezione apre il modulo tramite HTMX e aggiorna lo stato delle card.

Il proxy Django espone una sola `POST /api/assistant`, inoltrata a FastAPI
`POST /agent`. La pipeline Docker
copia gli artefatti di `dist-widget/` negli statici Django.

- [Runtime assistant-ui](https://www.assistant-ui.com/docs/runtimes/ag-ui/quickstart)
- [Integrazione FastAPI/LangGraph ufficiale](https://github.com/ag-ui-protocol/ag-ui/blob/main/integrations/langgraph/python/README.md)
