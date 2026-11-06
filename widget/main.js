import {createApp} from 'vue';
import {createI18n, i18nKey} from './i18n/index.js';
import AssistantApp from './components/AssistantApp.vue';
import './styles/widget.css';
import './styles/assistant-ui.css';

const root = document.getElementById('assistant-widget');
if (root) {
    // Aggira il bug di HTMX 1.9.10: più apostrofi negli ID dei campi rendono invalido il selettore dello swap standard.
    let htmxApi;
    window.htmx.defineExtension('ticket-form', {
        init(api) { htmxApi = api; },
        handleSwap(style, target, fragment, settleInfo) {
            if (style !== 'ticket-form' || target.id !== 'assistant-page-content') return false;
            // HTMX's delete swap cleans up listeners and timers without comparing field IDs.
            Array.from(target.children).forEach(child =>
                htmxApi.selectAndSwap('delete', child, child, '', settleInfo));
            const children = Array.from(fragment.childNodes);
            target.replaceChildren(fragment);
            // Returning the inserted nodes lets HTMX initialize them and emit its load events.
            return children;
        },
    });
    const csrfToken = root.querySelector('[name="csrfmiddlewaretoken"]').value;
    createApp(AssistantApp, {root, csrfToken})
        .provide(i18nKey, createI18n(root.dataset.language))
        .mount(root);
}
