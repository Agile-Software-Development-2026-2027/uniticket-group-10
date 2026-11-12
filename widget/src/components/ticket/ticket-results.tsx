import { useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { useI18n } from "../../i18n";
import { TicketCard, type Ticket } from "./ticket-card";

/** Mostra i ticket tre alla volta e sposta il focus sui nuovi risultati quando vengono espansi. */
export function TicketResults({ tickets }: { tickets: Ticket[] }) {
  const [visible, setVisible] = useState(3);
  const list = useRef<HTMLUListElement>(null);
  const t = useI18n();
  const count = Math.min(3, tickets.length - visible);
  return (
    <>
      {tickets.length > 0 && (
        <ul ref={list} className="assistant-results" aria-label={t("Richieste suggerite")}>
          {tickets.slice(0, visible).map((ticket) => (
            <TicketCard key={ticket.category_id} ticket={ticket} />
          ))}
        </ul>
      )}
      {count > 0 && (
        <button
          type="button"
          className="assistant-more"
          onClick={() => {
            const first = visible;
            setVisible(visible + 3);
            requestAnimationFrame(() =>
              list.current?.querySelectorAll("a")[first]?.focus({ preventScroll: true }),
            );
          }}
        >
          {t("Mostra un’altra richiesta", count)}
          <ChevronDown aria-hidden="true" />
        </button>
      )}
    </>
  );
}
