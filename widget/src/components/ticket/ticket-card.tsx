import { useEffect, useRef } from "react";
import { useAuiState } from "@assistant-ui/react";
import { ArrowRight } from "lucide-react";
import { useTicketFormContext } from "../../django/use-ticket-form";
import { useI18n } from "../../i18n";

export interface Ticket {
  category_id: number;
  title: string;
  structure_name: string;
  url: string;
}

/** Mostra una richiesta apribile con HTMX, indicando se il modulo è aperto o in caricamento. */
export function TicketCard({ ticket }: { ticket: Ticket }) {
  const link = useRef<HTMLAnchorElement>(null);
  const { selectedCategory, loadingCategory } = useTicketFormContext();
  const running = useAuiState((s) => s.thread.isRunning);
  const t = useI18n();
  const selected = String(ticket.category_id) === selectedCategory;
  const loading = String(ticket.category_id) === loadingCategory;
  useEffect(() => {
    if (link.current) window.htmx?.process(link.current);
  }, []);
  return (
    <li>
      <a
        ref={link}
        href={ticket.url}
        className={`assistant-card${selected ? " assistant-card--opened" : ""}`}
        data-ticket-id={ticket.category_id}
        data-structure-name={ticket.structure_name}
        hx-boost="true"
        hx-target="#assistant-page-content"
        hx-select="#assistant-page-content > *"
        hx-ext="ticket-form"
        hx-swap="ticket-form show:none"
        hx-sync="#assistant-root:replace"
        aria-current={selected ? "page" : undefined}
        aria-busy={loading}
        aria-disabled={running || selected}
        onClick={(e) => {
          if (running || selected) e.preventDefault();
        }}
      >
        <span className="assistant-card-details">
          <span className="assistant-card-title">{ticket.title}</span>
          {ticket.structure_name && (
            <small className="assistant-card-structure">{ticket.structure_name}</small>
          )}
          {loading ? (
            <small className="assistant-opened-label" role="status">
              {t("Caricamento modulo…")}
            </small>
          ) : (
            selected && <small className="assistant-opened-label">{t("Modulo aperto")}</small>
          )}
        </span>
        <ArrowRight aria-hidden="true" />
      </a>
    </li>
  );
}
