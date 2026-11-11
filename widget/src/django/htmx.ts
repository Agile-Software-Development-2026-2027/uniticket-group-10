interface SwapApi {
  selectAndSwap(
    style: string,
    target: Element,
    source: Element,
    response: string,
    settleInfo: unknown,
  ): void;
}
interface Htmx {
  process(element: Element): void;
  defineExtension(
    name: string,
    extension: {
      init(api: SwapApi): void;
      handleSwap(
        style: string,
        target: Element,
        fragment: DocumentFragment,
        settleInfo: unknown,
      ): ChildNode[] | false;
    },
  ): void;
}
declare global {
  interface Window {
    htmx?: Htmx;
  }
}
const registered = new WeakSet<Htmx>();
export function registerTicketSwap() {
  const htmx = window.htmx;
  if (!htmx || registered.has(htmx)) return;
  let api: SwapApi;
  htmx.defineExtension("ticket-form", {
    init(value) {
      api = value;
    },
    handleSwap(style, target, fragment, settleInfo) {
      if (style !== "ticket-form" || target.id !== "assistant-page-content") return false;
      // HTMX's delete swap also cleans up fields whose IDs contain apostrophes.
      Array.from(target.children).forEach((child) =>
        api.selectAndSwap("delete", child, child, "", settleInfo),
      );
      const children = Array.from(fragment.childNodes);
      target.replaceChildren(fragment);
      return children;
    },
  });
  registered.add(htmx);
}
