import { MarkdownTextPrimitive } from "@assistant-ui/react-markdown";
import remarkGfm from "remark-gfm";
import { useI18n } from "../i18n";

/** Renderizza il testo del messaggio in Markdown, con tabelle scorrevoli ed etichette tradotte. */
export function MarkdownText() {
  const t = useI18n();
  return (
    <MarkdownTextPrimitive
      className="assistant-markdown"
      remarkPlugins={[remarkGfm]}
      components={{
        em: ({ children }) => <>{children}</>,
        table: ({ children }) => (
          <div
            className="assistant-table-scroll"
            tabIndex={0}
            role="region"
            aria-label={t("Tabella")}
          >
            <table>{children}</table>
          </div>
        ),
      }}
    />
  );
}
