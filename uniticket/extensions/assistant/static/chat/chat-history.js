/** Incapsula cronologia e persistenza della scheda; non accede agli elementi HTML. */
export function createChatHistory(key, initialMessages = [], storage = null) {
    const roles = {user: 'Tu', assistant: 'Assistente', selection: 'selection'};
    // Mantiene compatibilità con i formati precedenti, filtra eventi validi e limita la cronologia.
    function normalize(messages) {
        return messages.filter(message => message && typeof message.text === 'string')
            .map(message => ({author: message.author || roles[message.kind], text: message.text}))
            .filter(message => ['Tu', 'Assistente', 'selection'].includes(message.author))
            // Le vecchie selezioni salvate come testo utente diventano eventi neutrali.
            .map(message => message.author === 'Tu' && message.text.startsWith('Ho selezionato: ')
                ? {author: 'selection', text: message.text.slice('Ho selezionato: '.length)} : message)
            .slice(-50);
    }
    // Lo stato resta privato alla factory; la chiave ricevuta distingue gli utenti nella scheda.
    let state = {history: initialMessages.map(text => ({author: 'Tu', text})),
        lastResponse: null, selectedId: null};
    try {
        // Ripristina anche l’ultima risposta API e la tipologia selezionata dopo un refresh.
        const saved = JSON.parse(storage?.getItem(key) || 'null');
        if (saved && Array.isArray(saved.history)) state = {
            history: normalize(saved.history),
            lastResponse: saved.lastResponse,
            selectedId: saved.selectedId == null ? null : String(saved.selectedId)
        };
    } catch (_) { /* Dati assenti o non leggibili non interrompono la conversazione. */ }

    // Errori o indisponibilità dello storage non bloccano gli aggiornamenti in memoria.
    function save() {
        try { storage?.setItem(key, JSON.stringify(state)); } catch (_) { /* Lo stato in memoria resta disponibile. */ }
    }

    return {
        // Restituisce copie dei messaggi, evitando modifiche esterne allo stato interno.
        get messages() { return state.history.map(message => ({...message})); },
        get selectedId() { return state.selectedId; },
        get lastResponse() { return state.lastResponse; },
        append(author, text) {
            state.history = normalize([...state.history, {author, text}]);
            save();
        },
        // Consente al coordinatore di ripristinare ticket o quick replies senza ripetere la ricerca.
        setResponse(response) { state.lastResponse = response; save(); },
        // Evita di duplicare la stessa selezione quando viene ripristinato il modulo già aperto.
        select(id, title) {
            const last = state.history.at(-1);
            if (state.selectedId === String(id) && last?.author === 'selection' && last.text === title) return;
            state.selectedId = String(id);
            state.history = normalize([...state.history, {author: 'selection', text: title}]);
            save();
        },
        // Il reset elimina sia i dati persistiti sia lo stato della conversazione corrente.
        clear() {
            state = {history: [], lastResponse: null, selectedId: null};
            try { storage?.removeItem(key); } catch (_) { /* Storage unavailable. */ }
        }
    };
}
