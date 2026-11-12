import { test } from "node:test";
import assert from "node:assert/strict";
import { readTicketResult } from "../src/components/tools/ticket-suggestions.tsx";
import { createI18n } from "../src/i18n/index.tsx";

test("unsupported languages fall back to English", () => {
  for (const language of ["fr", "de-DE", "es_ES"]) {
    const t = createI18n(language);
    assert.equal(t("Invia"), "Send");
    assert.equal(t("Mostra un’altra richiesta", 2), "Show 2 more requests");
  }
  assert.equal(createI18n("it-IT")("Invia"), "Invia");
  assert.equal(createI18n("en-US")("Invia"), "Send");
  assert.equal(createI18n()("Invia"), "Invia");
});

test("ticket results reject malformed data and unsafe URLs", () => {
  const ticket = {
    category_id: 1,
    title: "Certificato",
    structure_name: "Segreteria",
    url: "/ticket/1/",
  };
  assert.deepEqual(readTicketResult({ tickets: [ticket] }), { tickets: [ticket] });
  assert.deepEqual(readTicketResult(JSON.stringify({ tickets: [ticket] })), { tickets: [ticket] });
  assert.deepEqual(readTicketResult({ tickets: [] }), { tickets: [] });
  for (const url of [
    "//evil.test",
    "https://evil.test/",
    "/\\evil.test",
    "/ticket/\n1/",
    "/ticket/1/\n",
    "/ticket/\u0000",
    "/ticket/\u007f",
    "javascript:alert(1)",
  ])
    assert.equal(readTicketResult({ tickets: [{ ...ticket, url }] }), null);
  for (const result of [
    { message: 42, tickets: [] },
    null,
    "{",
    { tickets: [{}] },
    { tickets: [{ ...ticket, category_id: -1 }] },
  ])
    assert.equal(readTicketResult(result), null);
});
