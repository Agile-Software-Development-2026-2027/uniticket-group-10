import { AuiIf } from "@assistant-ui/react";
import { useI18n } from "../i18n";

// https://www.assistant-ui.com/docs/guides/context-api?utm_source=chatgpt.com#conditional-rendering
export function ChatLoading() {
  const t = useI18n();

  return (
    <AuiIf condition={(s) => s.thread.isRunning}>
      <div className="assistant-loading" role="status">
        <span className="assistant-loading-dots" aria-hidden="true">
          <span />
          <span />
          <span />
        </span>
        {t("Sto pensando…")}
      </div>
    </AuiIf>
  );
}
