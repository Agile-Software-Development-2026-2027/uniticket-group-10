import { createContext, useContext } from "react";
import it from "./it.json";
import en from "./en.json";

export function createI18n(language = "it") {
  const messages: Record<string, string | string[]> =
    language.toLowerCase().split(/[-_]/)[0] === "it" ? it : en;
  return (key: string, count = 1) => {
    const value = messages[key] ?? key;
    return (Array.isArray(value) ? value[count === 1 ? 0 : 1]! : value).replace(
      "%(count)s",
      String(count),
    );
  };
}
export const I18nContext = createContext(createI18n());
export const useI18n = () => useContext(I18nContext);
