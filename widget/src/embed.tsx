import { createRoot } from "react-dom/client";
import { Assistant, type AssistantOptions } from "./assistant";

export type WidgetOptions = AssistantOptions;
export function mountAssistantWidget(element: HTMLElement, options: WidgetOptions) {
  const root = createRoot(element);
  root.render(<Assistant {...options} />);
  return () => root.unmount();
}

const element = document.getElementById("assistant-widget");
if (element) {
  const csrfToken = element.querySelector<HTMLInputElement>('[name="csrfmiddlewaretoken"]')?.value;
  if (element.dataset.aguiUrl && csrfToken) {
    mountAssistantWidget(element, {
      apiUrl: element.dataset.aguiUrl,
      language: element.dataset.language,
      csrfToken,
    });
  } else {
    element.textContent = "Assistente non disponibile: configurazione mancante.";
  }
}
