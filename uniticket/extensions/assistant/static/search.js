/* One API call; two response shapes: tickets or clarify + quick_replies. */
(() => {
    'use strict';
    const form = document.getElementById('chatbot-search');
    if (!form) return;
    const input = form.querySelector('[name="message"]');
    const send = form.querySelector('[type="submit"]');
    const messages = document.getElementById('chatbot-messages');
    const results = document.getElementById('chatbot-results');
    const replies = document.getElementById('chatbot-quick-replies');
    const status = document.getElementById('chatbot-search-status');
    let busy = false;
    const storageKey = form.dataset.chatKey;
    let history = [...messages.querySelectorAll('.chatbot-message')].slice(1).map(message => ({
        author: message.querySelector('strong').textContent,
        text: message.querySelector('p').textContent
    }));
    let lastResponse = null;
    let selectedId = null;

    function saveChat() {
        try {
            sessionStorage.setItem(storageKey, JSON.stringify({history, lastResponse, selectedId}));
        } catch (_) { /* Chat remains usable when browser storage is unavailable. */ }
    }

    function addMessage(author, text, remember = true) {
        const message = document.createElement('div');
        message.className = author === 'selection' ? 'chatbot-selection'
            : 'chatbot-message' + (author === 'Tu' ? ' chatbot-message-user' : '');
        const label = document.createElement(author === 'selection' ? 'span' : 'strong');
        label.textContent = author === 'selection' ? 'Tipologia selezionata' : author;
        const paragraph = document.createElement('p');
        paragraph.textContent = text;
        message.append(label, paragraph);
        messages.append(message);
        messages.scrollTop = messages.scrollHeight;
        if (remember) {
            history.push({author, text});
            history = history.slice(-50);
            saveChat();
        }
    }

    function renderResponse(data) {
        results.replaceChildren();
        replies.replaceChildren();
        if (Array.isArray(data.tickets)) {
            for (const ticket of data.tickets) {
                const link = document.createElement('a');
                const url = new URL(results.dataset.workspaceUrl, location.origin);
                url.searchParams.set('ticket_id', ticket.id);
                url.hash = 'chatbot-request-panel';
                link.href = url.href;
                link.dataset.ticketId = ticket.id;
                link.className = 'chatbot-result';
                link.textContent = ticket.title;
                results.append(link);
            }
        } else if (typeof data.clarify === 'string' && Array.isArray(data.quick_replies)) {
            for (const reply of data.quick_replies) {
                const button = document.createElement('button');
                button.type = 'button';
                button.className = 'chatbot-quick-reply';
                button.textContent = reply;
                button.dataset.query = reply;
                replies.append(button);
            }
        }
    }

    // Tab-scoped history survives opening a module, refresh and browser Back.
    // The API remains a stateless mock; no extra endpoint is needed.
    try {
        const saved = JSON.parse(sessionStorage.getItem(storageKey));
        if (saved && Array.isArray(saved.history)) {
            history = saved.history.filter(item => item &&
                ['Tu', 'Assistente', 'selection'].includes(item.author) && typeof item.text === 'string')
                .map(item => item.author === 'Tu' && item.text.startsWith('Ho selezionato: ')
                    ? {author: 'selection', text: item.text.slice('Ho selezionato: '.length)} : item)
                .slice(-50);
            selectedId = saved.selectedId;
            lastResponse = saved.lastResponse;
            if (Array.isArray(lastResponse?.tickets)) {
                lastResponse.tickets = lastResponse.tickets.filter(ticket => ticket.id !== 320);
            }
            while (messages.children.length > 1) messages.lastElementChild.remove();
            history.forEach(item => addMessage(item.author, item.text, false));
            if (lastResponse) renderResponse(lastResponse);
            saveChat();
        }
    } catch (_) { /* Ignore unavailable storage or an invalid saved conversation. */ }
    if (results.dataset.selectedId && selectedId !== results.dataset.selectedId) {
        selectedId = results.dataset.selectedId;
        addMessage('selection', results.dataset.selectedTitle);
    }
    results.addEventListener('click', event => {
        const link = event.target.closest('a[data-ticket-id]');
        if (!link || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        selectedId = link.dataset.ticketId;
        addMessage('selection', link.textContent);
    });
    document.querySelector('[data-reset-chat]').addEventListener('submit', () => {
        try { sessionStorage.removeItem(storageKey); } catch (_) { /* No saved state. */ }
    });

    async function search(query) {
        if (busy) return;
        query = query.trim();
        if (!query) return;
        busy = true;
        send.disabled = true;
        input.readOnly = true;
        replies.querySelectorAll('button').forEach(button => { button.disabled = true; });
        status.textContent = 'Ricerca in corso…';
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 15000);
        try {
            const response = await fetch(form.dataset.searchUrl, {
                method: 'POST',
                mode: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': form.querySelector('[name="csrfmiddlewaretoken"]').value
                },
                body: JSON.stringify({query}),
                signal: controller.signal
            });
            if (!response.ok) throw new Error('Ricerca non riuscita. Riprova o ricarica la pagina.');
            const data = await response.json();
            const isTickets = Array.isArray(data.tickets);
            const isClarify = typeof data.clarify === 'string' && Array.isArray(data.quick_replies);
            if (!isTickets && !isClarify) throw new Error('Risposta API non valida.');
            addMessage('Tu', query);
            lastResponse = data;
            renderResponse(data);
            addMessage('Assistente', isTickets
                ? (data.tickets.length ? 'Ecco le tipologie di richiesta disponibili nella demo.'
                    : 'Nessun risultato. Prova a riformulare la richiesta.')
                : data.clarify);
            input.value = '';
            status.textContent = 'Risposta ricevuta.';
        } catch (error) {
            status.textContent = error.name === 'AbortError'
                ? 'Tempo di attesa scaduto. Riprova.' : 'Ricerca non riuscita. Riprova o ricarica la pagina.';
        } finally {
            clearTimeout(timeout);
            busy = false;
            send.disabled = false;
            input.readOnly = false;
            replies.querySelectorAll('button').forEach(button => { button.disabled = false; });
            input.focus();
        }
    }

    form.addEventListener('submit', event => {
        event.preventDefault();
        search(input.value);
    });
    replies.addEventListener('click', event => {
        const button = event.target.closest('button[data-query]');
        if (button) search(button.dataset.query);
    });
})();
