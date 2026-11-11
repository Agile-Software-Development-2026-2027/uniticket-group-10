import { ComposerPrimitive, useAuiState } from "@assistant-ui/react";
import { ArrowUp, Square } from "lucide-react";
import { useI18n } from "../i18n";
import { useTicketFormContext } from "../django/use-ticket-form";

/** Gestisce input, invio, stop ed errori di caricamento dei moduli. */
// https://www.assistant-ui.com/docs/primitives/composer
export function ChatComposer() {
  const t = useI18n();
  const running = useAuiState((s) => s.thread.isRunning);
  const form = useTicketFormContext();
  return (
    <>
      {form.error && (
        <p className="assistant-status assistant-error" role="alert">
          {form.error}
        </p>
      )}
      <ComposerPrimitive.Root className="assistant-form">
        <div className="assistant-compose">
          <ComposerPrimitive.Input
            rows={1}
            maxLength={500}
            placeholder={t("Scrivi la tua richiesta…")}
            aria-label={t("Scrivi la tua richiesta…")}
          />
          {running ? (
            <ComposerPrimitive.Cancel className="assistant-send" aria-label={t("Interrompi")}>
              <Square aria-hidden="true" />
            </ComposerPrimitive.Cancel>
          ) : (
            <ComposerPrimitive.Send className="assistant-send" aria-label={t("Invia")}>
              <ArrowUp aria-hidden="true" />
            </ComposerPrimitive.Send>
          )}
        </div>
      </ComposerPrimitive.Root>
    </>
  );
}
