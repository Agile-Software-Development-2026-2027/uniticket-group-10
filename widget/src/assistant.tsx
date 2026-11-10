import { useMemo, type ReactNode } from "react";
import { AssistantRuntimeProvider, AuiConfig, Tools } from "@assistant-ui/react";
import { useAgUiRuntime } from "@assistant-ui/react-ag-ui";
import { HttpAgent } from "@ag-ui/client";

import { createI18n, I18nContext } from "./i18n";
import { createDjangoFetch } from "./django/fetch";
import { TicketFormContext, useTicketForm } from "./django/use-ticket-form";
import { assistantToolkit } from "./tools";
import { Widget } from "./components/widget";
import "./styles/widget.css";

export interface AssistantOptions {
  apiUrl?: string;
  csrfToken?: string;
  language?: string;
}

type AssistantProps = AssistantOptions & {
  children?: ReactNode;
};

export function Assistant({ language = "it", children, ...options }: AssistantProps) {
  const t = useMemo(() => createI18n(language), [language]);

  return (
    <I18nContext.Provider value={t}>
      <AssistantSession {...options}>{children}</AssistantSession>
    </I18nContext.Provider>
  );
}

function AssistantSession({ apiUrl = "/api/assistant", csrfToken = "", children }: AssistantProps) {
  const request = useMemo(() => createDjangoFetch(csrfToken), [csrfToken]);
  const agent = useMemo(() => new HttpAgent({ url: apiUrl, fetch: request }), [apiUrl, request]);
  const runtime = useAgUiRuntime({ agent });

  return (
    <AssistantRuntimeProvider
      runtime={runtime}
      config={AuiConfig({
        tools: Tools({
          toolkit: assistantToolkit,
        }),
      })}
    >
      <TicketForm>
        {children}
        <Widget />
      </TicketForm>
    </AssistantRuntimeProvider>
  );
}

function TicketForm({ children }: { children?: ReactNode }) {
  const form = useTicketForm();

  return <TicketFormContext.Provider value={form}>{children}</TicketFormContext.Provider>;
}
