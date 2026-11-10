import { useEffect, useId, useRef, useState } from "react";
import { ThreadListPrimitive, useAui } from "@assistant-ui/react";
import { MessageCircle, SquarePen, X } from "lucide-react";
import { usePanelResize } from "../hooks/use-panel-resize";
import { useI18n } from "../i18n";
import { ChatThread } from "./chat-thread";

/** Mostra launcher e pannello ridimensionabile, gestendo apertura, focus e nuova chat. */
export function Widget() {
  const [open, setOpen] = useState(false);
  const panel = useRef<HTMLElement>(null);
  const launcher = useRef<HTMLButtonElement>(null);
  const panelId = useId();
  const titleId = useId();
  const resize = usePanelResize(panel);
  const t = useI18n();
  const aui = useAui();
  useEffect(() => {
    if (open) panel.current?.querySelector("textarea")?.focus();
  }, [open]);
  const close = () => {
    setOpen(false);
    launcher.current?.focus();
  };
  return (
    <div className={`assistant-widget${open ? " assistant-widget--open" : ""}`}>
      <section
        ref={panel}
        id={panelId}
        className="assistant-panel"
        hidden={!open}
        inert={!open}
        aria-hidden={!open}
        aria-labelledby={titleId}
        role="region"
        onKeyDown={(e) => {
          if (e.key === "Escape" && open) {
            e.preventDefault();
            close();
          }
        }}
      >
        <button
          type="button"
          className="assistant-resize"
          aria-controls={panelId}
          aria-label={t("Ridimensiona la chat")}
          title={t("Trascina o usa i tasti freccia per ridimensionare")}
          aria-keyshortcuts="ArrowUp ArrowDown ArrowLeft ArrowRight"
          {...resize}
        />
        <header className="assistant-header">
          <h2 id={titleId}>{t("Assistente UniTicket")}</h2>
          <div className="assistant-header-actions">
            <ThreadListPrimitive.New
              className="assistant-header-button"
              aria-label={t("Nuova chat")}
              title={t("Nuova chat")}
              onClick={() => {
                void aui.thread.cancelRun();
                requestAnimationFrame(() => panel.current?.querySelector("textarea")?.focus());
              }}
            >
              <SquarePen aria-hidden="true" />
            </ThreadListPrimitive.New>
            <button
              type="button"
              className="assistant-header-button"
              aria-label={t("Chiudi l'assistente")}
              onClick={close}
            >
              <X aria-hidden="true" />
            </button>
          </div>
        </header>
        <ChatThread />
      </section>
      <button
        ref={launcher}
        type="button"
        className="assistant-launcher"
        aria-controls={panelId}
        aria-expanded={open}
        onClick={() => (open ? close() : setOpen(true))}
      >
        <span className="assistant-launcher-icon" aria-hidden="true">
          <MessageCircle className="assistant-launcher-chat" />
          <X className="assistant-launcher-close" />
        </span>
        {t("Assistente")}
      </button>
    </div>
  );
}
