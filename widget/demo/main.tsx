import { createRoot } from "react-dom/client";
import { useState } from "react";
import { Assistant } from "../src/assistant";
import { DemoPage } from "./page";
import { installDemoHtmx } from "./htmx";
import { createAgUiFixture } from "./agui-fixture";
import { respondToDemo } from "./scenarios";
import "./styles.css";

const fixture = createAgUiFixture(respondToDemo);
window.fetch = (input, init) => {
  const url = new URL(input instanceof Request ? input.url : String(input), window.location.href);
  if (
    url.origin !== window.location.origin ||
    !["/api/assistant", "/api/assistant/thread/new/"].includes(url.pathname)
  ) {
    return Promise.reject(new Error("Unexpected request outside the local demo"));
  }
  return fixture(input, init);
};
installDemoHtmx();

/** Keeps language controls and scenarios in the real assistant runtime provider. */
function Demo() {
  const [language, setLanguage] = useState("it");
  return (
    <Assistant key={language} apiUrl="/api/assistant" csrfToken="demo-csrf" language={language}>
      <DemoPage language={language} onLanguageChange={setLanguage} />
    </Assistant>
  );
}

export function mountDemo(element: HTMLElement) {
  const root = createRoot(element);
  root.render(<Demo />);
  return () => root.unmount();
}

const element = document.getElementById("demo-root");
if (element) mountDemo(element);
