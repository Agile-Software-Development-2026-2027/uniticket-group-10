import { ActionBarPrimitive, MessagePrimitive } from "@assistant-ui/react";
import { useI18n } from "../../i18n";
import { MarkdownText } from "../markdown-text";
import { ToolFallback } from "../tools/tool-fallback";

export function AssistantMessage() {
  const t = useI18n();
  return (
    <MessagePrimitive.Root className="assistant-msg assistant-msg--assistant">
      <span className="assistant-author">{t("Assistente")}</span>
      <MessagePrimitive.Parts>
        {/* https://www.assistant-ui.com/docs/primitives/message#core-concepts */}
        {({ part }) => {
          if (part.type === "text") return <MarkdownText />;
          {/* Se non registri il renderer del tool dentro tool.tsx viene mostrato quello di fallback */}
          if (part.type === "tool-call") return part.toolUI ?? <ToolFallback {...part} />;

          return null;
        }}
      </MessagePrimitive.Parts>
      <MessagePrimitive.Error>
        <p className="assistant-error" role="alert">{t("La ricerca non è riuscita. Riprova tra poco.")}</p>
        <ActionBarPrimitive.Root>
          <ActionBarPrimitive.Reload className="assistant-retry">
            {t("Riprova")}
          </ActionBarPrimitive.Reload>
        </ActionBarPrimitive.Root>
      </MessagePrimitive.Error>
    </MessagePrimitive.Root>
  );
}
