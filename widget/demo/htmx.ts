// Simulates Django form loading while keeping the widget's HTMX listeners unchanged.
export function installDemoHtmx() {
  window.htmx = {
    defineExtension() {},
    process(element) {
      element.addEventListener("click", (event) => {
        if (event.defaultPrevented || !(element instanceof HTMLAnchorElement)) return;
        event.preventDefault();
        const target = document.getElementById("assistant-page-content");
        if (!target) return;
        const xhr = new XMLHttpRequest();
        Object.defineProperty(xhr, "status", { value: 200 });
        const detail = { target, elt: element, xhr };
        document.dispatchEvent(new CustomEvent("htmx:beforeSend", { detail }));
        setTimeout(() => {
          if (!target.isConnected) return;
          const marker = document.createElement("div");
          marker.dataset.assistantModule = "";
          marker.dataset.categoryId = element.dataset.ticketId;
          const title = document.createElement("h3");
          title.textContent =
            element.querySelector(".assistant-card-title")?.textContent ?? "Modulo demo";
          const label = document.createElement("label");
          label.textContent = "Descrizione della richiesta (solo demo)";
          const textarea = document.createElement("textarea");
          textarea.rows = 4;
          label.append(textarea);
          const note = document.createElement("p");
          note.textContent = "Modulo simulato: i dati non vengono inviati né salvati.";
          marker.append(title, label, note);
          target.replaceChildren(marker);
          document.dispatchEvent(new CustomEvent("htmx:afterSwap", { detail }));
          document.dispatchEvent(new CustomEvent("htmx:afterRequest", { detail }));
        }, 150);
      });
    },
  };
}
