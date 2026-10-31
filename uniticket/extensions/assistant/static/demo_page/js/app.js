/* Interfaccia a pagina intera: coordina chat, risultati e modulo della richiesta selezionata. */
(() => {
    'use strict';
    const root = document.getElementById('assistant-page-app');
    if (!root) return;
    const modules = AssistantModules('chatbot-request-content', 'assistant-page-content');
    Vue.createApp({
        // Delimitatori diversi da quelli Django per evitare conflitti nei template.
        delimiters: ['[[', ']]'],
        mixins: [AssistantChat(root)],
        data: () => ({view: 'chat', share: 40, hasModule: false, selectedTicketId: '', moduleUrl: ''}),
        computed: {
            // Mostra i risultati dell’ultima risposta che contiene un elenco di richieste.
            results() { return this.tickets(this.history.findLast(entry => Array.isArray(entry.replies)) || {}); },
        },
        mounted() {
            window.addEventListener('popstate', this.restoreModule);
            if (root.dataset.initialModuleUrl) this.loadModule(root.dataset.initialModuleUrl, false);
        },
        beforeUnmount() { modules.cancel(); window.removeEventListener('popstate', this.restoreModule); },
        methods: {
            ticketUrl(ticket) { return ticket.url || root.dataset.ticketListUrl; },
            selectTicket(event, ticket) {
                if (!ticket.url) return;
                // Lascia al browser i clic modificati, per esempio Ctrl/cmd + clic per una nuova scheda.
                if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
                event.preventDefault();
                // Riaprire la selezione attuale conserva i campi già compilati nel modulo.
                if (String(ticket.ticket_id) === this.selectedTicketId) {
                    if (this.view !== 'split') this.view = 'request';
                } else this.loadModule(this.ticketUrl(ticket), true, ticket.ticket_id);
            },
            async loadModule(url, push = true, ticketId = '') {
                this.loadingTicketId = String(ticketId);
                this.moduleStatus = '';
                try {
                    const result = await modules.load(new URL(url, window.location.origin).href, false);
                    if (!result) return;
                    this.moduleUrl = result.url;
                    this.selectedTicketId = result.categoryId;
                    this.hasModule = result.hasModule;
                    this.view = result.hasModule ? 'split' : 'chat';
                    this.loadingTicketId = '';
                    // L’URL della demo resta condivisibile, mentre il form proviene dalla rotta originale.
                    const state = {moduleUrl: result.url};
                    if (push) window.history.pushState(state, '', root.dataset.workspaceUrl.replace(/\/0$/, '/' + encodeURIComponent(result.categoryId)));
                    else window.history.replaceState(state, '', window.location.href);
                    this.moduleStatus = '';
                } catch (_) {
                    this.loadingTicketId = '';
                    this.moduleStatus = 'Impossibile aprire il modulo. Seleziona di nuovo la richiesta.';
                }
            },
            // Allinea il modulo all’URL quando si usano Indietro e Avanti nel browser.
            restoreModule(event) {
                const url = event.state?.moduleUrl;
                if (url) {
                    if (url !== this.moduleUrl) this.loadModule(url, false);
                } else {
                    modules.cancel();
                    this.moduleUrl = '';
                    this.selectedTicketId = '';
                    this.hasModule = false;
                    this.view = 'chat';
                    this.loadingTicketId = '';
                    this.moduleStatus = '';
                }
            },
            // Limita la quota della chat per lasciare spazio utilizzabile a entrambi i pannelli.
            resize(value) { this.share = Math.min(70, Math.max(35, value)); },
            drag(event) {
                if (!event.currentTarget.hasPointerCapture(event.pointerId)) return;
                const bounds = this.$refs.workspace.getBoundingClientRect();
                this.resize(100 * (event.clientX - bounds.left) / bounds.width);
            },
            stopDrag(event) {
                if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
            },
            // Rende il separatore regolabile anche da tastiera, senza trascinamento del mouse.
            resizeKey(event) {
                const sizes = {ArrowLeft: this.share - 2, ArrowRight: this.share + 2, Home: 35, End: 70, Enter: 40};
                if (!(event.key in sizes)) return;
                event.preventDefault();
                this.resize(sizes[event.key]);
            },
        },
    }).mount(root);
})();
