import {inject} from 'vue';
import it from './it.json';
import en from './en.json';

export const i18nKey = Symbol('widget-i18n');

export function createI18n(language = 'it') {
    const locale = language.toLowerCase().split(/[-_]/)[0];
    const messages = locale === 'en' ? en : it;
    return {
        gettext(key, values = {}) {
            let text = messages[key] ?? it[key] ?? key;
            if (Array.isArray(text)) text = text[values.count === 1 ? 0 : 1];
            return text.replace(/%\((\w+)\)s/g, (placeholder, name) =>
                Object.hasOwn(values, name) ? String(values[name]) : placeholder);
        },
    };
}

export const useI18n = () => inject(i18nKey);
