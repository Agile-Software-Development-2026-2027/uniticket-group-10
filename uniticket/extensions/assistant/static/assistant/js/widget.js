/* Conversazione nella scheda corrente; le ricerche passano dall'API Django. */
(() => {
    'use strict';
    const widget = document.getElementById('assistant-widget');
    if (!widget) return;

    const launcher = widget.querySelector('.assistant-launcher');
    const panel = widget.querySelector('.assistant-panel');
    const messages = widget.querySelector('.assistant-messages');
    const status = widget.querySelector('.assistant-status');
    const form = widget.querySelector('.assistant-form');
    const input = form.querySelector('textarea');
    const sendButton = form.querySelector('button');
    const csrfToken = form.querySelector('[name="csrfmiddlewaretoken"]').value;
    const mobile = window.matchMedia('(max-width: 576px)');
    const welcome = {author: 'bot', text: 'Ciao! Descrivi cosa ti serve e ti suggerisco la richiesta giusta. Ad esempio: “Mi serve un certificato di iscrizione”.'};
    let history = [];
    let pending = null;
    let opener = launcher;
    let previousOverflow = null;
    let scrollPosition = null;

    function save() {
        if (!panel.hidden) scrollPosition = messages.scrollTop;
        try {
            sessionStorage.setItem(widget.dataset.storageKey, JSON.stringify({
                history, open: !panel.hidden, scrollTop: scrollPosition,
            }));
        } catch (_) { /* La chat funziona anche se lo storage non è disponibile. */ }
    }

    function render(entry) {
        const nearBottom = messages.scrollHeight - messages.scrollTop - messages.clientHeight < 80;
        const bubble = document.createElement('div');
        bubble.className = 'assistant-msg assistant-msg--' + entry.author;
        const author = document.createElement('span');
        author.className = 'assistant-author';
        author.textContent = entry.author === 'user' ? 'Tu' : 'Assistente';
        const text = document.createElement('p');
        text.textContent = entry.text;
        if (entry.error) text.className = 'assistant-error';
        bubble.append(author, text);
        const results = document.createElement('ul');
        results.className = 'assistant-results';
        const tickets = (entry.replies || []).filter(reply => reply?.type === 'ticket');
        results.setAttribute('aria-label', 'Richieste suggerite');
        function appendTickets(limit) {
            for (const reply of tickets.slice(results.childElementCount, limit)) {
                const item = document.createElement('li');
                const link = document.createElement('a');
                link.className = 'assistant-card';
                link.href = widget.dataset.openUrl + '?ticket_id=' + encodeURIComponent(reply.ticket_id);
                link.addEventListener('click', save);
                const title = document.createElement('span');
                title.textContent = reply.title;
                if (reply.structure_name) {
                    const structure = document.createElement('small');
                    structure.className = 'assistant-card-structure';
                    structure.textContent = reply.structure_name;
                    title.append(structure);
                }
                if (widget.dataset.loadedTicketId === String(reply.ticket_id)) {
                    link.className += ' assistant-card--opened';
                    link.setAttribute('aria-current', 'page');
                    const opened = document.createElement('small');
                    opened.className = 'assistant-opened-label';
                    opened.textContent = 'Modulo aperto';
                    title.append(opened);
                }
                const arrow = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
                arrow.setAttribute('viewBox', '0 0 24 24');
                arrow.setAttribute('aria-hidden', 'true');
                const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                path.setAttribute('d', 'M5 12h14m-6-6 6 6-6 6');
                arrow.append(path);
                link.append(title, arrow);
                item.append(link);
                results.append(item);
            }
        }
        const visible = Number.isInteger(entry.visibleTickets) ? Math.max(3, entry.visibleTickets) : 3;
        appendTickets(Math.min(visible, tickets.length));
        if (results.childElementCount) bubble.append(results);
        if (tickets.length > 3) {
            const more = document.createElement('button');
            more.type = 'button';
            more.className = 'assistant-more';
            const moreLabel = document.createElement('span');
            moreLabel.textContent = 'Mostra altre richieste';
            const count = document.createElement('span');
            count.className = 'assistant-more-count';
            count.setAttribute('aria-hidden', 'true');
            const chevron = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            chevron.setAttribute('viewBox', '0 0 24 24');
            chevron.setAttribute('aria-hidden', 'true');
            const chevronPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            chevronPath.setAttribute('d', 'm6 9 6 6 6-6');
            chevron.append(chevronPath);
            more.append(moreLabel, count, chevron);
            function updateMore() {
                const remaining = tickets.length - results.childElementCount;
                more.hidden = remaining === 0;
                count.textContent = String(remaining);
                more.setAttribute('aria-label', `Mostra altre richieste, ${remaining} ancora disponibili`);
            }
            more.addEventListener('click', () => {
                const firstNew = results.childElementCount;
                appendTickets(firstNew + 3);
                entry.visibleTickets = results.childElementCount;
                updateMore();
                // Mantiene la navigazione da tastiera sui risultati appena aggiunti.
                results.children[firstNew]?.children[0].focus({preventScroll: true});
                save();
            });
            updateMore();
            bubble.append(more);
        }
        if (entry.retryQuery) {
            const retry = document.createElement('button');
            retry.type = 'button';
            retry.className = 'assistant-retry';
            retry.textContent = 'Riprova la ricerca';
            retry.addEventListener('click', () => {
                if (pending) return;
                input.value = entry.retryQuery;
                resizeInput();
                search(entry.retryQuery);
            });
            bubble.append(retry);
        }
        messages.append(bubble);
        if (entry.author === 'user') {
            messages.scrollTop = messages.scrollHeight;
        } else if (nearBottom && !panel.hidden) {
            // Porta in vista l'inizio della risposta, senza saltare in fondo ai ticket.
            const padding = parseFloat(window.getComputedStyle(messages).paddingTop) || 0;
            messages.scrollTop += bubble.getBoundingClientRect().top - messages.getBoundingClientRect().top - padding;
        }
    }

    function add(entry) {
        history.push(entry);
        render(entry);
        save();
    }

    function syncViewport() {
        const modal = mobile.matches && !panel.hidden;
        panel.setAttribute('role', modal ? 'dialog' : 'region');
        if (modal) {
            panel.setAttribute('aria-modal', 'true');
            if (previousOverflow === null) previousOverflow = document.body.style.overflow;
            document.body.style.overflow = 'hidden';
        } else {
            panel.removeAttribute('aria-modal');
            if (previousOverflow !== null) document.body.style.overflow = previousOverflow;
            previousOverflow = null;
        }
        const viewport = window.visualViewport;
        panel.style.height = modal && viewport ? viewport.height + 'px' : '';
        panel.style.top = modal && viewport ? viewport.offsetTop + 'px' : '';
    }

    function setOpen(open, trigger, focus = true) {
        if (!panel.hidden) scrollPosition = messages.scrollTop;
        if (open && panel.hidden) opener = trigger || document.activeElement;
        panel.hidden = !open;
        launcher.setAttribute('aria-expanded', String(open));
        launcher.setAttribute('aria-label', open ? "Chiudi l'assistente UniTicket" : "Apri l'assistente UniTicket");
        syncViewport();
        if (open) {
            resizeInput();
            messages.scrollTop = scrollPosition ?? messages.scrollHeight;
            if (focus) input.focus({preventScroll: true});
        } else if (opener && opener.isConnected) {
            opener.focus({preventScroll: true});
        }
        save();
    }

    function resizeInput() {
        // Prima azzera l'altezza per ridurla anche quando si cancella del testo.
        input.style.height = 'auto';
        input.style.height = Math.min(128, Math.max(44, input.scrollHeight)) + 'px';
    }

    function setBusy(busy) {
        sendButton.disabled = busy;
        input.readOnly = busy;
        status.textContent = busy ? 'Sto cercando le richieste più pertinenti…' : '';
    }

    function reset() {
        if (pending) pending.abort();
        pending = null;
        setBusy(false);
        input.value = '';
        resizeInput();
        history = [];
        messages.replaceChildren();
        add(welcome);
        input.focus();
    }

    async function search(query) {
        if (pending) return;
        const controller = new AbortController();
        pending = controller;
        const timeout = setTimeout(() => controller.abort(), 30000);
        add({author: 'user', text: query});
        setBusy(true);
        try {
            const response = await fetch(widget.dataset.searchUrl, {
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
                body: JSON.stringify({query}),
                signal: controller.signal,
            });
            if (pending !== controller) return;
            if (response.status === 401 || response.status === 403) {
                throw new Error('La sessione è scaduta: ricarica la pagina e accedi di nuovo.');
            }
            if (!response.ok) throw new Error('La ricerca non è riuscita. Riprova tra poco.');
            const data = await response.json();
            if (pending !== controller) return;
            if (!Array.isArray(data.tickets)) throw new Error('La risposta non è valida. Riprova tra poco.');
            add({
                author: 'bot',
                text: data.tickets.length ? 'Ecco le richieste che potrebbero fare al caso tuo. Seleziona quella che vuoi aprire.'
                    : 'Non ho trovato richieste adatte. Prova a indicare il servizio o il documento di cui hai bisogno.',
                replies: data.tickets,
            });
            input.value = '';
            resizeInput();
        } catch (error) {
            if (pending !== controller) return;
            add({author: 'bot', error: true, retryQuery: query,
                text: error.name === 'AbortError' ? 'La ricerca sta impiegando troppo tempo. Riprova.'
                    : error.name === 'TypeError' ? 'Impossibile contattare il server. Controlla la connessione e riprova.' : error.message});
        } finally {
            clearTimeout(timeout);
            if (pending === controller) {
                pending = null;
                setBusy(false);
            }
        }
    }

    launcher.addEventListener('click', () => setOpen(panel.hidden, launcher));
    messages.addEventListener('scroll', () => {
        if (!panel.hidden) scrollPosition = messages.scrollTop;
    }, {passive: true});
    window.addEventListener('pagehide', save);
    widget.querySelector('.assistant-close').addEventListener('click', () => setOpen(false));
    widget.querySelector('.assistant-reset').addEventListener('click', reset);
    form.addEventListener('submit', event => {
        event.preventDefault();
        const query = input.value.trim();
        if (query && !pending) search(query);
    });
    input.addEventListener('input', resizeInput);
    input.addEventListener('keydown', event => {
        if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
            event.preventDefault();
            form.requestSubmit();
        }
    });
    document.addEventListener('keydown', event => {
        if (panel.hidden) return;
        if (event.key === 'Escape') {
            event.preventDefault();
            setOpen(false);
        }
        if (event.key === 'Tab' && mobile.matches) {
            const focusable = [...panel.querySelectorAll('button:not(:disabled), a[href], textarea')];
            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            if (event.shiftKey && (document.activeElement === first || !panel.contains(document.activeElement))) {
                event.preventDefault(); last.focus();
            } else if (!event.shiftKey && (document.activeElement === last || !panel.contains(document.activeElement))) {
                event.preventDefault(); first.focus();
            }
        }
    });
    document.addEventListener('click', event => {
        const link = event.target.closest('[data-assistant-open]');
        if (!link) return;
        event.preventDefault();
        setOpen(true, link);
    });
    mobile.addEventListener('change', syncViewport);
    if (window.visualViewport) {
        window.visualViewport.addEventListener('resize', syncViewport);
        window.visualViewport.addEventListener('scroll', syncViewport);
    }

    let saved = {};
    try { saved = JSON.parse(sessionStorage.getItem(widget.dataset.storageKey)) || {}; } catch (_) { /* Nessuna cronologia recuperabile. */ }
    history = Array.isArray(saved.history) ? saved.history.filter(entry =>
        entry && ['user', 'bot'].includes(entry.author) && typeof entry.text === 'string' &&
        (!entry.replies || Array.isArray(entry.replies))) : [];
    if (history.length) history.forEach(render); else add(welcome);
    scrollPosition = Number.isFinite(saved.scrollTop) && saved.scrollTop >= 0 ? saved.scrollTop : null;
    // Ripristina la lettura senza spostare focus o tastiera sulla nuova pagina.
    if (saved.open) setOpen(true, launcher, false);
})();
