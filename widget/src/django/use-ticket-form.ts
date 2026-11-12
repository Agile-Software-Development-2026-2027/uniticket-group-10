import { createContext, useContext, useEffect, useState } from "react";
import { useI18n } from "../i18n";
import { registerTicketSwap } from "./htmx";

type Detail = {
  target?: HTMLElement;
  elt?: HTMLElement;
  xhr?: XMLHttpRequest;
  failed?: boolean;
  error?: unknown;
};
export function useTicketForm() {
  const [selectedCategory, select] = useState("");
  const [loadingCategory, loading] = useState("");
  const [error, setError] = useState("");
  const t = useI18n();
  useEffect(() => {
    registerTicketSwap();
    let request: XMLHttpRequest | undefined;
    let disposed = false;
    const loaded = (event?: Event) => {
      const page = document.getElementById("assistant-page-content");
      if (
        event?.type === "htmx:afterSwap" &&
        (event as CustomEvent<Detail>).detail?.target !== page
      )
        return;
      const marker = page?.querySelector<HTMLElement>("[data-assistant-module]");
      const form = page?.querySelector<HTMLFormElement>(
        'form[method="post"][enctype="multipart/form-data"]',
      );
      if (form && marker?.dataset.url) {
        const url = new URL(marker.dataset.url, window.location.href);
        if (url.origin === window.location.origin) form.action = url.href;
      }
      select(marker?.dataset.categoryId || "");
    };
    const finished = (event: Event) => {
      const detail = (event as CustomEvent<Detail>).detail ?? {};
      if (disposed || !request || detail.xhr !== request) return;
      if (detail.failed || detail.error || request.status === 0 || request.status >= 400)
        setError(t("Il caricamento del modulo non è riuscito. Riprova."));
      request = undefined;
      loading("");
    };
    const start = (event: Event) => {
      const detail = (event as CustomEvent<Detail>).detail ?? {};
      if (detail.target?.id !== "assistant-page-content") return;
      setError("");
      request = detail.xhr;
      loading(detail.elt?.closest<HTMLElement>("a[data-ticket-id]")?.dataset.ticketId || "");
      request?.addEventListener("loadend", () => finished(event), { once: true });
    };
    const events = {
      "htmx:afterSwap": loaded,
      "htmx:historyRestore": loaded,
      "htmx:beforeSend": start,
      "htmx:afterRequest": finished,
      "htmx:onLoadError": finished,
    };
    Object.entries(events).forEach(([name, handler]) => document.addEventListener(name, handler));
    loaded();
    return () => {
      disposed = true;
      Object.entries(events).forEach(([name, handler]) =>
        document.removeEventListener(name, handler),
      );
    };
  }, [t]);
  return { selectedCategory, loadingCategory, error };
}
export const TicketFormContext = createContext({
  selectedCategory: "",
  loadingCategory: "",
  error: "",
});
export const useTicketFormContext = () => useContext(TicketFormContext);
