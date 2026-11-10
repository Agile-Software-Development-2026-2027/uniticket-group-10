import { useEffect, useRef } from "react";
import { useAui, useAuiState } from "@assistant-ui/react";
import { ArrowUpRight, MessageCircle } from "lucide-react";
import { demoScenarios } from "./scenarios";

type Props = { language: string; onLanguageChange: (language: string) => void };

/** Provides local scenarios and an HTMX target around the unchanged widget. */
export function DemoPage({ language, onLanguageChange }: Props) {
  const aui = useAui();
  const running = useAuiState((s) => s.thread.isRunning);
  const page = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (page.current)
      page.current.textContent =
        "Apri una card dei ticket nella chat per visualizzare qui il modulo simulato.";
  }, []);
  const showChat = () =>
    document
      .querySelector<HTMLButtonElement>(".assistant-launcher[aria-expanded='false']")
      ?.click();
  const run = (id: string) => {
    showChat();
    aui.thread.append({
      role: "user",
      content: [{ type: "text", text: `/${id}` }],
    });
  };
  return (
    <main id="assistant-root" className="demo-page">
      <header className="demo-header">
        <div>
          <h1>Prova l’assistente UniTicket</h1>
          <p>Una conversazione di esempio per verificare il widget, le card e i moduli.</p>
        </div>
        <button className="demo-open" onClick={showChat}>
          <MessageCircle aria-hidden="true" />
          Apri la chat
        </button>
      </header>
      <div className="demo-toolbar">
        <p role="status">
          {running
            ? "Risposta in corso: puoi interromperla dalla chat."
            : "Demo locale · nessuna chiamata a Django o al modello"}
        </p>
        <label>
          Lingua del widget{" "}
          <select
            aria-label="Lingua del widget"
            value={language}
            onChange={(event) => onLanguageChange(event.target.value)}
          >
            <option value="it">Italiano</option>
            <option value="en">English</option>
          </select>
        </label>
      </div>
      <div className="demo-columns">
        <section aria-labelledby="demo-scenarios-title">
          <h2 id="demo-scenarios-title">Scegli cosa provare</h2>
          <p>
            Ogni scenario invia un messaggio nella conversazione corrente. Puoi anche scrivere
            direttamente nella chat.
          </p>
          <div className="demo-scenarios">
            {demoScenarios.map((scenario) => (
              <button
                type="button"
                key={scenario.id}
                data-demo-scenario={scenario.id}
                disabled={running}
                onClick={() => run(scenario.id)}
              >
                <span>
                  <strong>{scenario.title}</strong>
                  <small>{scenario.description}</small>
                </span>
                <ArrowUpRight aria-hidden="true" />
              </button>
            ))}
          </div>
        </section>
        <section className="demo-form-panel" aria-labelledby="demo-form-title">
          <h2 id="demo-form-title">Il modulo selezionato</h2>
          <div ref={page} id="assistant-page-content" />
          <p className="demo-note">
            L’apertura del modulo rimane nella pagina e non invia notifiche all’agente. Cambiare
            lingua avvia una nuova chat.
          </p>
        </section>
      </div>
    </main>
  );
}
