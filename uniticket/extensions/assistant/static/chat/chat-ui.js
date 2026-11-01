import {createApp, nextTick, reactive} from 'vue';

/** Gestisce lo stato e la vista della chat; il modulo Django resta fuori dalle regioni Vue. */
export function mountChatUI({workspaceUrl, onQuickReply, onTicketSelect}) {
    // Stato privato condiviso dai tre punti di montaggio: messaggi, input e suggerimenti.
    const state = reactive({messages: [], query: '', busy: false,
        tickets: [], quickReplies: [], hasResponse: false});
    // I template HTML restano in chatbot.html; ogni applicazione riceve lo stesso stato reattivo.
    const options = template => ({template, setup: () => ({state})});
    createApp(options('#chatbot-messages-template')).mount('#chatbot-messages');
    createApp(options('#chatbot-composer-template')).mount('#chatbot-composer');

    // Il link reale consente accesso diretto e navigazione anche senza caricamento HTMX.
    function ticketUrl(ticket) {
        const url = new URL(workspaceUrl, location.origin);
        url.searchParams.set('ticket_id', ticket.id);
        url.hash = 'chatbot-request-panel';
        return url.href;
    }
    // La vista comunica il testo scelto; la chiamata HTTP appartiene al coordinatore.
    function requestSearch(query) {
        if (!state.busy) onQuickReply(query);
    }
    function selectTicket(ticket, event) {
        // I clic con modificatori mantengono la navigazione prevista dal browser.
        if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        // true indica che il pannello ha preso in carico l’azione e la pagina non deve navigare.
        if (onTicketSelect(ticket)) event.preventDefault();
    }
    createApp({
        template: '#chatbot-suggestions-template',
        setup: () => ({state, ticketUrl, requestSearch, selectTicket})
    }).mount('#chatbot-suggestions');

    // Interfaccia pubblica: il coordinatore usa metodi senza modificare direttamente state.
    return {
        get query() { return state.query.trim(); },
        setMessages(messages) {
            // Le copie evitano riferimenti condivisi con gli oggetti della cronologia.
            state.messages = messages.map(message => ({...message}));
            // Lo scorrimento avviene dopo che Vue ha aggiornato i messaggi nel DOM.
            nextTick(() => {
                const panel = document.getElementById('chatbot-messages');
                panel.scrollTop = panel.scrollHeight;
            });
        },
        // Sostituisce entrambe le liste: un chiarimento non deve lasciare visibili vecchi ticket.
        setResponse(response) {
            state.tickets = (response.tickets || []).map(ticket => ({...ticket}));
            state.quickReplies = [...(response.quick_replies || [])];
            // Distingue l’avvio della demo da una risposta valida con zero risultati.
            state.hasResponse = true;
        },
        setBusy(busy) { state.busy = busy; },
        clearQuery() { state.query = ''; },
        focusInput() { document.getElementById('chatbot-query').focus(); }
    };
}
