/* Stato Vue condiviso da pagina e widget; la conversazione resta nella scheda del browser. */
window.AssistantChat = function (root) {
    const key = root.dataset.storageKey;
    const csrf = root.querySelector('[name="csrfmiddlewaretoken"]').value;
    let saved = {};
    let pending = null;
    // Se lo storage è vuoto, non valido o inaccessibile, la chat parte senza dati salvati.
    try { saved = JSON.parse(sessionStorage.getItem(key)) || {}; } catch (_) {}
    // Recupera i messaggi validi, elimina le vecchie notifiche di selezione e uniforma gli autori.
    const history = Array.isArray(saved.history) ? saved.history.filter(entry =>
        entry && ['user', 'bot', 'Tu', 'Assistente'].includes(entry.author) && typeof entry.text === 'string' &&
        !(['user', 'Tu'].includes(entry.author) && entry.text.startsWith('Ho selezionato: '))
    ).map(entry => ({...entry, author: ['user', 'Tu'].includes(entry.author) ? 'user' : 'bot'})) : [];
    // Recupera anche i risultati salvati nel formato precedente della demo pagina.
    if (saved.lastResponse?.tickets && history.at(-1)?.author === 'bot') history.at(-1).replies = saved.lastResponse.tickets;
    return {
        data: () => ({history, query: typeof saved.query === 'string' ? saved.query : '', busy: false, open: Boolean(saved.open), moduleStatus: '', loadingTicketId: ''}),
        computed: {
            status() { return this.busy ? 'Sto cercando le richieste più pertinenti…' : this.moduleStatus; },
        },
        watch: {
            // Conserva la bozza mentre viene scritta, anche prima di chiudere il widget o cambiare pagina.
            query: 'saveChat',
        },
        mounted() {
            this.$nextTick(this.scrollToLastUserMessage);
            // Salva anche quando si lascia la pagina, prima che il browser la nasconda.
            window.addEventListener('pagehide', this.saveChat);
        },
        beforeUnmount() {
            if (pending) pending.abort();
            pending = null;
            window.removeEventListener('pagehide', this.saveChat);
        },
        methods: {
            // All’apertura riparte dall’ultima domanda, lasciando la risposta subito sotto.
            scrollToLastUserMessage() {
                const index = this.history.findLastIndex(entry => entry.author === 'user');
                const messages = this.$refs.messages;
                const entry = messages?.querySelector('[data-entry="' + index + '"]');
                if (entry) messages.scrollTop += entry.getBoundingClientRect().top - messages.getBoundingClientRect().top;
            },
            saveChat() {
                try { sessionStorage.setItem(key, JSON.stringify({history: this.history, open: this.open, query: this.query})); } catch (_) {}
            },
            tickets(entry) { return Array.isArray(entry.replies) ? entry.replies.filter(ticket => ticket?.type === 'ticket') : []; },
            // Invia la ricerca al backend e aggiunge domanda e risposta alla cronologia locale.
            async search(value = this.query) {
                const query = value.trim();
                if (!query || this.busy) return;
                const controller = new AbortController();
                pending = controller;
                this.busy = true;
                this.history.push({author: 'user', text: query});
                await this.$nextTick();
                this.$refs.messages.scrollTop = this.$refs.messages.scrollHeight;
                this.saveChat();
                let followResponse = false;
                try {
                    // Il token CSRF protegge la POST; il controller permette di annullarla al reset.
                    const {data} = await axios.post(root.dataset.searchUrl, {query}, {
                        headers: {'X-CSRFToken': csrf}, signal: controller.signal, timeout: 30000,
                    });
                    if (pending !== controller) return;
                    if (!Array.isArray(data.tickets)) throw new Error('Risposta API non valida. Riprova.');
                    const messages = this.$refs.messages;
                    // Segui la risposta solo se l’utente non è risalito a leggere messaggi precedenti.
                    followResponse = messages.scrollHeight - messages.scrollTop - messages.clientHeight < 80;
                    this.history.push({author: 'bot', text: data.tickets.length
                        ? 'Ecco le richieste che potrebbero fare al caso tuo. Seleziona quella che vuoi aprire.'
                        : 'Non ho trovato richieste adatte. Prova a riformulare la richiesta.', replies: data.tickets});
                    this.query = '';
                } catch (error) {
                    if (pending !== controller) return;
                    const status = error.response?.status;
                    const text = [401, 403].includes(status) ? 'La sessione è scaduta: ricarica la pagina e accedi di nuovo.'
                        : error.code === 'ECONNABORTED' ? 'Tempo di attesa scaduto. Riprova.'
                        : 'La ricerca non è riuscita. Riprova tra poco.';
                    this.history.push({author: 'bot', text, error: true, retryQuery: query});
                } finally {
                    // Una richiesta annullata non deve modificare lo stato di una ricerca successiva.
                    if (pending === controller) {
                        pending = null;
                        this.busy = false;
                        // Limita la cronologia salvata agli ultimi 50 messaggi.
                        this.history = this.history.slice(-50);
                        await this.$nextTick();
                        if (followResponse) {
                            const messages = this.$refs.messages;
                            const entry = [...messages.querySelectorAll('[data-entry]')].at(-1);
                            if (entry) messages.scrollTop += entry.getBoundingClientRect().top - messages.getBoundingClientRect().top;
                        }
                        if (document.activeElement === document.body) this.$refs.input?.focus({preventScroll: true});
                        this.saveChat();
                    }
                }
            },
            // Annulla la ricerca in corso prima di svuotare e salvare la conversazione.
            resetChat() {
                if (pending) pending.abort();
                pending = null;
                this.history = [];
                this.query = '';
                this.busy = false;
                this.moduleStatus = '';
                this.$nextTick(() => { this.saveChat(); this.$refs.input?.focus({preventScroll: true}); });
            },
        },
    };
};
