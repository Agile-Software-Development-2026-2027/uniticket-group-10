import {createFormPanel} from './form-panel.js?v=assistant-submit-2';
import {mountChatUI} from './chat/chat-ui.js?v=assistant-submit-2';
import {searchTickets} from './chat/chat-api.js?v=assistant-submit-2';
import {createChatHistory} from './chat/chat-history.js?v=assistant-submit-2';

// Coordinatore della chat: collega moduli indipendenti senza costruire il loro HTML.
const form = document.getElementById('chatbot-search');
if (form) {
    const suggestions = document.getElementById('chatbot-suggestions');
    const status = document.getElementById('chatbot-search-status');
    // I messaggi server arrivano da json_script; sessionStorage può contenere una cronologia più recente.
    const initialMessages = JSON.parse(document.getElementById('assistant-initial-messages').textContent);
    let storage = null;
    try { storage = window.sessionStorage; } catch (_) { /* La cronologia resta utilizzabile in memoria. */ }
    const history = createChatHistory(form.dataset.chatKey, initialMessages, storage);
    // Le callback traducono le azioni Vue in ricerca o caricamento del pannello.
    const ui = mountChatUI({
        workspaceUrl: suggestions.dataset.workspaceUrl,
        onQuickReply: query => search(query),
        onTicketSelect: ticket => formPanel.load(ticket)
    });
    const formPanel = createFormPanel({
        fragmentUrl: suggestions.dataset.formUrl,
        workspaceUrl: suggestions.dataset.workspaceUrl,
        // La selezione viene registrata soltanto dopo il caricamento riuscito del modulo.
        onSelected: ticket => {
            history.select(ticket.id, ticket.title);
            ui.setMessages(history.messages);
        }
    });
    // Questi flag evitano ricerche sovrapposte e aggiornamenti dopo un reset.
    let busy = false;
    let resetting = false;
    let controller = null;

    // L’accesso diretto tramite ticket_id deve comparire anche nella cronologia della chat.
    if (suggestions.dataset.selectedId && history.selectedId !== suggestions.dataset.selectedId) {
        history.select(suggestions.dataset.selectedId, suggestions.dataset.selectedTitle);
    }
    ui.setMessages(history.messages);
    if (history.lastResponse) ui.setResponse(history.lastResponse);

    // Esegue una ricerca e aggiorna cronologia, messaggi e suggerimenti con la stessa risposta.
    async function search(query) {
        query = query.trim();
        if (busy || resetting || !query) return;
        busy = true;
        ui.setBusy(true);
        status.textContent = 'Ricerca in corso…';
        // Limita l’attesa a 15 secondi e permette al reset di interrompere la richiesta.
        controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 15000);
        try {
            const data = await searchTickets(form.dataset.searchUrl, query,
                form.querySelector('[name="csrfmiddlewaretoken"]').value, controller.signal);
            if (resetting) return;
            // I messaggi vengono aggiunti solo quando la risposta API è stata ricevuta e validata.
            history.append('Tu', query);
            history.setResponse(data);
            // Il chiarimento usa il testo del backend; i risultati della demo hanno messaggi dedicati.
            history.append('Assistente', 'clarify' in data ? data.clarify : data.tickets.length
                ? 'Ecco le tipologie di richiesta disponibili nella demo.'
                : 'Nessun risultato. Prova a riformulare la richiesta.');
            ui.setMessages(history.messages);
            ui.setResponse(data);
            ui.clearQuery();
            status.textContent = 'Risposta ricevuta.';
        } catch (error) {
            if (!resetting) status.textContent = error.name === 'AbortError'
                ? 'Tempo di attesa scaduto. Riprova.' : 'Ricerca non riuscita. Riprova o ricarica la pagina.';
        } finally {
            // Ripristina i comandi anche in caso di errore, evitando di riattivarli durante il reset.
            clearTimeout(timeout);
            busy = false;
            if (!resetting) {
                ui.setBusy(false);
                ui.focusInput();
            }
        }
    }

    // La ricerca aggiorna la chat tramite JSON, senza il normale ricaricamento del form HTML.
    form.addEventListener('submit', event => { event.preventDefault(); search(ui.query); });
    // Il reset pulisce la scheda e interrompe le richieste prima del normale POST a Django.
    document.querySelector('[data-reset-chat]').addEventListener('submit', () => {
        resetting = true;
        formPanel.cancel();
        controller?.abort();
        history.clear();
    });
}
