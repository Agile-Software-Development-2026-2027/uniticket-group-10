/* Widget dell'assistente con Vue: lo stato è qui, l'HTML è in templates/assistant/widget.html. */
(() => {
    'use strict';
    const element = document.getElementById('assistant-widget');
    if (!element || !window.Vue) return;

    // Legge gli attributi data-* scritti da django (indirizzi, token CSRF, ecc.) e li mette in un oggetto.
    const config = {...element.dataset};
    const welcome = () => ({
        author: 'bot',
        text: 'Ciao! Descrivi cosa ti serve e ti suggerisco la richiesta giusta. Ad esempio: “Mi serve un certificato di iscrizione”.',
    });

    Vue.createApp({
        delimiters: ['[[', ']]'],

        /* è lo stato. Tutto quello che compare nel template (open,loading,query,messages,openUrl) è qua */ 
        data() {
            return {
                open: false,
                loading: false,
                query: '',
                messages: [],
                openUrl: config.openUrl,
            };
        },

        // ogni volta che messages o open cambiano, si salva.
        // deep:true serve a vedere anche le modifiche dentro i messaggi, come visible che aqumenta con "Mostra altre"
        watch: {
            // Ogni modifica alla conversazione o all'apertura viene salvata nella scheda.
            messages: {handler() { this.save(); }, deep: true},
            open() { this.save(); },
        },

        methods: {
            save() {
                try {
                    sessionStorage.setItem(config.storageKey, JSON.stringify({messages: this.messages, open: this.open}));
                } catch (_) { /* senza storage la chat funziona, ma non viene ricordata */ }
            },

            load() {
                try {
                    return JSON.parse(sessionStorage.getItem(config.storageKey)) || {};
                } catch (_) {
                    return {};
                }
            },

            // chiamata dall'html da vue, per aprire la chat. Fa open=true, scrolla in basso, ridimensiona la casella e mette il focus.
            show() {
                this.open = true;
                this.$nextTick(() => {
                    this.scrollToBottom();
                    this.resizeInput();
                    this.$refs.input.focus();
                });
            },

            close() {
                this.open = false;
            },

            reset() {
                this.messages = [welcome()];
                this.query = '';
                this.$nextTick(this.resizeInput);
            },

            isOpened(ticket) {
                return config.loadedTicketId === String(ticket.ticket_id);
            },

            scrollToBottom() {
                const box = this.$refs.messages;
                box.scrollTop = box.scrollHeight;
            },

            resizeInput() {
                // Prima azzera l'altezza, così la casella si riduce anche quando si cancella del testo.
                const input = this.$refs.input;
                input.style.height = 'auto';
                input.style.height = Math.min(128, Math.max(44, input.scrollHeight)) + 'px';
            },

            add(message) {
                this.messages.push(message);
                this.$nextTick(this.scrollToBottom);
            },

            // chiamata dall'html da vue, quando si preme invio. Se la query non è vuota e non è in caricamento, chiama search(query)
            send() {
                const query = this.query.trim();
                if (query && !this.loading) this.search(query);
            },

            // stessa logica di prima. NON TOCCA MAI L'HTML. Fa solo this.add(...) e cambia loading, e Vue aggiorna la pagina
            async search(query) {
                this.add({author: 'user', text: query});
                this.loading = true;
                const controller = new AbortController();
                const timeout = setTimeout(() => controller.abort(), 30000);
                try {
                    const response = await fetch(config.searchUrl, {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json', 'X-CSRFToken': config.csrfToken},
                        body: JSON.stringify({query}),
                        signal: controller.signal,
                    });
                    if (response.status === 401 || response.status === 403) {
                        throw new Error('La sessione è scaduta: ricarica la pagina e accedi di nuovo.');
                    }
                    if (!response.ok) throw new Error('La ricerca non è riuscita. Riprova tra poco.');
                    const data = await response.json();
                    if (!Array.isArray(data.tickets)) throw new Error('La risposta non è valida. Riprova tra poco.');
                    this.add({
                        author: 'bot',
                        tickets: data.tickets,
                        visible: 3,
                        text: data.tickets.length
                            ? 'Ecco le richieste che potrebbero fare al caso tuo. Seleziona quella che vuoi aprire.'
                            : 'Non ho trovato richieste adatte. Prova a indicare il servizio o il documento di cui hai bisogno.',
                    });
                    this.query = '';
                    this.$nextTick(this.resizeInput);
                } catch (error) {
                    this.add({
                        author: 'bot',
                        error: true,
                        retryQuery: query,
                        text: error.name === 'AbortError' ? 'La ricerca sta impiegando troppo tempo. Riprova.'
                            : error.name === 'TypeError' ? 'Impossibile contattare il server. Controlla la connessione e riprova.'
                            : error.message,
                    });
                } finally {
                    clearTimeout(timeout);
                    this.loading = false;
                }
            },
        },
        
        mounted() {
            // Ripristina la conversazione salvata nella scheda, oppure parte dal benvenuto.
            const saved = this.load();
            this.messages = Array.isArray(saved.messages) && saved.messages.length ? saved.messages : [welcome()];
            this.open = Boolean(saved.open);
            this.$nextTick(this.scrollToBottom);

            // Il bottone "Assistente" della navbar apre il widget invece di cambiare pagina.
            document.addEventListener('click', event => {
                if (!event.target.closest('[data-assistant-open]')) return;
                event.preventDefault();
                this.show();
            });
            document.addEventListener('keydown', event => {
                if (event.key === 'Escape' && this.open) this.close();
            });
        },
    }).mount(element);
})();
