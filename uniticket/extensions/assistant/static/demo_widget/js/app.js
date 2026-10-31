/* Widget flottante: aggiunge apertura, navigazione e comportamento mobile alla chat condivisa. */
(() => {
    'use strict';
    const root = document.getElementById('assistant-widget');
    if (!root) return;
    const modules = AssistantModules('assistant-page-content');
    const mobile = window.matchMedia('(max-width: 576px)');
    let previousOverflow = null;
    let opener = null;
    let navigated = false;
    Vue.createApp({
        // Evita che le espressioni Vue vengano confuse con quelle dei template Django.
        delimiters: ['[[', ']]'],
        mixins: [AssistantChat(root)],
        data: () => ({mobile: mobile.matches, viewport: {}, loadedTicketId: root.dataset.loadedTicketId || ''}),
        watch: {
            open() {
                this.syncViewport();
                if (this.open) this.$nextTick(this.scrollToLastUserMessage);
                this.saveChat();
            },
            query() { this.$nextTick(this.resizeInput); },
        },
        mounted() {
            mobile.addEventListener('change', this.syncViewport);
            // Il viewport visibile cambia anche quando si apre la tastiera virtuale sul telefono.
            window.visualViewport?.addEventListener('resize', this.syncViewport);
            window.visualViewport?.addEventListener('scroll', this.syncViewport);
            window.addEventListener('popstate', this.restoreModule);
            document.addEventListener('keydown', this.keydown);
            this.syncViewport();
            this.$nextTick(this.resizeInput);
        },
        beforeUnmount() {
            modules.cancel();
            mobile.removeEventListener('change', this.syncViewport);
            window.visualViewport?.removeEventListener('resize', this.syncViewport);
            window.visualViewport?.removeEventListener('scroll', this.syncViewport);
            window.removeEventListener('popstate', this.restoreModule);
            document.removeEventListener('keydown', this.keydown);
            if (previousOverflow !== null) document.body.style.overflow = previousOverflow;
        },
        methods: {
            // Le conversazioni precedenti prive di URL restano consultabili dal percorso di selezione originale.
            ticketUrl(ticket) { return ticket.url || root.dataset.ticketListUrl; },
            selectTicket(event, ticket) {
                if (!ticket.url) return;
                // Mantiene il comportamento nativo dei clic modificati e dei pulsanti secondari.
                if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
                event.preventDefault();
                if (String(ticket.ticket_id) !== this.loadedTicketId) this.loadModule(this.ticketUrl(ticket), true, ticket.ticket_id);
            },
            async loadModule(url, push = true, ticketId = '') {
                this.loadingTicketId = String(ticketId);
                this.moduleStatus = '';
                try {
                    const result = await modules.load(new URL(url, window.location.origin).href, push);
                    if (!result) return;
                    this.loadedTicketId = result.categoryId;
                    this.loadingTicketId = '';
                    navigated = true;
                    this.saveChat();
                } catch (_) {
                    this.loadingTicketId = '';
                    this.moduleStatus = 'Impossibile aprire il modulo. Seleziona di nuovo la richiesta.';
                }
            },
            // Ripristina il contenuto solo dopo una navigazione gestita dal widget.
            restoreModule() { if (navigated) this.loadModule(window.location.href, false); },
            toggle(open = !this.open) {
                this.saveChat();
                // Alla chiusura restituisce il focus all’elemento che aveva aperto il widget.
                if (open) opener = document.activeElement;
                this.open = open;
                this.$nextTick(() => {
                    if (open) { this.resizeInput(); this.$refs.input.focus({preventScroll: true}); }
                    else (opener?.isConnected ? opener : this.$refs.launcher).focus({preventScroll: true});
                });
            },
            syncViewport() {
                this.mobile = mobile.matches;
                const modal = this.open && this.mobile;
                // Su mobile il widget aperto blocca lo scorrimento della pagina sottostante.
                if (modal) {
                    if (previousOverflow === null) previousOverflow = document.body.style.overflow;
                    document.body.style.overflow = 'hidden';
                } else if (previousOverflow !== null) {
                    document.body.style.overflow = previousOverflow;
                    previousOverflow = null;
                }
                // Adatta altezza e posizione allo spazio visibile sopra la tastiera virtuale.
                const viewport = window.visualViewport;
                this.viewport = modal && viewport ? {height: viewport.height + 'px', top: viewport.offsetTop + 'px'} : {};
            },
            resizeInput() {
                const input = this.$refs.input;
                // Prima azzera l’altezza per permettere alla textarea anche di restringersi.
                input.style.height = 'auto';
                input.style.height = Math.min(128, Math.max(44, input.scrollHeight)) + 'px';
            },
            // Aggiunge tre risultati e porta il focus sul primo appena mostrato.
            async showMore(entry, index) {
                const firstNew = entry.visibleTickets || 3;
                entry.visibleTickets = Math.min(this.tickets(entry).length, (entry.visibleTickets || 3) + 3);
                await this.$nextTick();
                const links = this.$refs.messages.querySelectorAll('[data-entry="' + index + '"] .assistant-card');
                links[firstNew]?.focus({preventScroll: true});
                this.saveChat();
            },
            keydown(event) {
                if (!this.open) return;
                if (event.key === 'Escape') { event.preventDefault(); this.toggle(false); }
                // Nel widget mobile il tasto Tab mantiene il focus dentro il pannello modale.
                if (event.key !== 'Tab' || !this.mobile) return;
                const items = [...this.$refs.panel.querySelectorAll('button:not(:disabled), a[href], textarea')];
                const first = items[0], last = items.at(-1);
                if (event.shiftKey && (document.activeElement === first || !this.$refs.panel.contains(document.activeElement))) {
                    event.preventDefault(); last?.focus();
                } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
            },
        },
    }).mount(root);
})();
