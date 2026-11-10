import { AuiIf, ThreadPrimitive } from "@assistant-ui/react";
import { ArrowDown } from "lucide-react";
import { useI18n } from "../i18n";
import { AssistantMessage } from "./message/assistant-message";
import { UserMessage } from "./message/user-message";
import { ChatComposer } from "./chat-composer";
import { ChatLoading } from "./chat-loading";

/** Organizza la conversazione: benvenuto, messaggi, attesa, errori e composer. */
export function ChatThread() {
  const t = useI18n();
  return (
    <ThreadPrimitive.Root className="assistant-thread">
      <ThreadPrimitive.Viewport
        className="assistant-messages"
        role="log"
        aria-label={t("Assistente")}
      >
        <AuiIf condition={(s) => s.thread.isEmpty}>
          <div className="assistant-msg assistant-msg--assistant">
            <span className="assistant-author">{t("Assistente")}</span>
            <p>
              {t(
                'Ciao! Descrivi ciò di cui hai bisogno e ti suggerirò la richiesta più adatta. Ad esempio: "Ho bisogno di un certificato di iscrizione"',
              )}
            </p>
          </div>
        </AuiIf>
        <ThreadPrimitive.Messages>
          {({ message }) => (message.role === "user" ? <UserMessage /> : <AssistantMessage />)}
        </ThreadPrimitive.Messages>
        <ChatLoading />
        <ThreadPrimitive.ScrollToBottom
          behavior="auto"
          className="assistant-jump"
          aria-label={t("Vai agli ultimi messaggi")}
        >
          <ArrowDown aria-hidden="true" />
        </ThreadPrimitive.ScrollToBottom>
      </ThreadPrimitive.Viewport>
      <ChatComposer />
    </ThreadPrimitive.Root>
  );
}
