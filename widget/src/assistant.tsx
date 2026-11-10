import { useEffect, useMemo, useState, type ReactNode } from "react";
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

// Django is responsible for creating thread IDs.
async function createThread(request: typeof fetch): Promise<string> {
  const response = await request("/api/assistant/thread/new/", { method: "POST" });

  if (!response.ok) {
    throw new Error("Failed to create assistant thread");
  }

  const data: { thread_id: string } = await response.json();

  if (!data.thread_id) {
    throw new Error("Missing thread_id");
  }

  return data.thread_id;
}

function AssistantSession({ apiUrl = "/api/assistant", csrfToken = "", children }: AssistantProps) {
  const request = useMemo(() => createDjangoFetch(csrfToken), [csrfToken]);

  const url = useMemo(() => new URL(apiUrl, window.location.href), [apiUrl]);

  if (url.origin !== window.location.origin) {
    throw new Error("Expected a same-origin Django endpoint");
  }

  const [threadId, setThreadId] = useState<string | null>(null);

  const [error, setError] = useState<string | null>(null);

  // Create the initial thread through Django.
  useEffect(() => {
    let active = true;

    createThread(request)
      .then((id) => {
        if (active) setThreadId(id);
      })
      .catch(() => {
        if (active) {
          setError("Unable to start assistant session");
        }
      });

    return () => {
      active = false;
    };
  }, [request]);

  if (error) {
    return <div role="alert">{error}</div>;
  }

  if (!threadId) {
    return <div>Loading assistant...</div>;
  }

  return (
    <ActiveAssistantSession
      key={url.href}
      url={url.href}
      request={request}
      initialThreadId={threadId}
    >
      {children}
    </ActiveAssistantSession>
  );
}

function ActiveAssistantSession({
  url,
  request,
  initialThreadId,
  children,
}: {
  url: string;
  request: typeof fetch;
  initialThreadId: string;
  children?: ReactNode;
}) {
  const [threadId, setThreadId] = useState(initialThreadId);

  const agent = useMemo(
    () =>
      new HttpAgent({
        url,
        fetch: request,
        threadId,
      }),
    [url, request, threadId],
  );

  const runtime = useAgUiRuntime({
    agent,
    adapters: {
      threadList: {
        threadId,

        onSwitchToNewThread: async () => {
          const next = await createThread(request);
          agent.threadId = next;
          setThreadId(next);
        },
      },
    },
  });

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
