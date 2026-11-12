import { MessagePartPrimitive, MessagePrimitive } from "@assistant-ui/react";
import { useI18n } from "../../i18n";

export function UserMessage() {
  const t = useI18n();
  return (
    <MessagePrimitive.Root className="assistant-msg assistant-msg--user">
      <span className="assistant-author">{t("Tu")}</span>
      <MessagePrimitive.Parts>
        {({ part }) => {
          if (part.type === "text") return <MessagePartPrimitive.Text component="p" />;
          return null;
        }}
      </MessagePrimitive.Parts>
    </MessagePrimitive.Root>
  );
}
