import type { ToolCallMessagePartComponent } from "@assistant-ui/react";
import { Check, Clock, LoaderCircle, Pause, X } from "lucide-react";
import { useI18n } from "../../i18n";

const stateIcons = {
  "In corso…": LoaderCircle,
  Completata: Check,
  "Non riuscita": X,
  Interrotta: Pause,
  "In attesa": Clock,
};

/** Mostra nome e stato tradotti dei tool senza risultati visualizzabili con un renderer dedicato. */
export const ToolFallback: ToolCallMessagePartComponent = ({ toolName, status, isError }) => {
  const t = useI18n();
  const labelKey = `tool.${toolName}`;
  const label = t(labelKey);
  const state =
    isError || (status.type === "incomplete" && status.reason === "error")
      ? "Non riuscita"
      : status.type === "running"
        ? "In corso…"
        : status.type === "complete"
          ? "Completata"
          : status.type === "incomplete"
            ? "Interrotta"
            : "In attesa";
  return (
    <div className="assistant-tool" role="status" data-error={state === "Non riuscita"}>
      <span className="assistant-tool-icon" aria-hidden="true" title={t(state)}>
        {Object.entries(stateIcons).map(([name, Icon]) => (
          <Icon
            key={name}
            data-active={state === name}
            className={name === "In corso…" ? "assistant-tool-spinner" : undefined}
          />
        ))}
      </span>
      <span>{label === labelKey ? t("Attività dell’assistente") : label}</span>
      <span
        className="assistant-tool-state"
        data-hidden={state !== "Interrotta"}
      >
        {t(state)}
      </span>
    </div>
  );
};
