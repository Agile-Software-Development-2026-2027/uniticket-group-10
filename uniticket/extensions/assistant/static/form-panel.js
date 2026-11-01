import {confirmFormReplacement} from './form-confirmation.js?v=assistant-submit-2';
import {createFormChanges} from './form-changes.js?v=assistant-submit-2';

/** Incapsula caricamento e invio del pannello. Vue comunica tramite load() e onSelected. */
export function createFormPanel({fragmentUrl, workspaceUrl, onSelected}) {
    const slot = document.getElementById('chatbot-form-slot');
    const status = document.getElementById('chatbot-form-status');
    // Stato privato: una selezione o un invio alla volta, con controllo delle modifiche correnti.
    let pending = null;
    let submitting = false;
    let changes = createFormChanges(null);

    // Inizializza i calendari presenti nel nuovo HTML, soltanto se il plugin è disponibile.
    function initializeWidgets() {
        const panel = slot.querySelector('#chatbot-request-panel');
        const $ = window.jQuery;
        if (!panel || !$?.fn.datetimepicker) return;
        $(panel).find('.uniticket-datetimepicker').each(function () {
            // Lo stesso elemento non deve ricevere due inizializzazioni del widget.
            if (!$(this).data('DateTimePicker')) $(this).datetimepicker({
                format: panel.dataset.datetimeFormat,
                showTodayButton: true,
                locale: panel.dataset.language
            });
        });
    }
    // Configura il form originale dopo il primo rendering e dopo ogni aggiornamento HTML.
    function prepareForm() {
        const panel = slot.querySelector('#chatbot-request-panel');
        const form = panel?.querySelector('form');
        if (form) {
            form.action = panel.dataset.submitUrl; // Destinazione del normale invio senza HTMX.
            const url = new URL(fragmentUrl, location.origin);
            url.searchParams.set('ticket_id', panel.dataset.ticketId);
            // La POST restituisce un frammento; il target comprende soltanto il pannello del modulo.
            form.setAttribute('hx-post', url.href);
            form.setAttribute('hx-target', '#chatbot-form-slot');
            form.setAttribute('hx-swap', 'innerHTML');
            // Multipart conserva il supporto agli allegati; sync limita gli invii sovrapposti del form.
            form.setAttribute('hx-encoding', 'multipart/form-data');
            form.setAttribute('hx-sync', 'this:drop');
            form.setAttribute('hx-request', '{"timeout":15000}');
            // HTMX deve elaborare gli attributi aggiunti dopo l’inserimento del form.
            window.htmx?.process(form);
            // Conserva il comportamento UniTicket: Invio negli input non invia accidentalmente il form.
            for (const type of ['keyup', 'keypress']) form.addEventListener(type, event => {
                if (event.target.matches('input') && event.key === 'Enter') event.preventDefault();
            });
        }
        // Un form restituito con errori contiene dati non salvati e rimane protetto.
        changes = createFormChanges(form, {initiallyDirty: panel?.dataset.bound === 'true'});
        return panel;
    }
    // Gli eventi HTMX risalgono nel DOM: vengono gestite soltanto richieste destinate a questo slot.
    function isPanelRequest(event) {
        return event.detail.target === slot;
    }
    // Configura anche il modulo eventualmente presente nell’accesso diretto con ticket_id.
    prepareForm();
    initializeWidgets();

    // I widget vengono inizializzati quando HTMX ha completato l’assestamento del nuovo HTML.
    slot.addEventListener('htmx:afterSettle', event => {
        if (isPanelRequest(event)) initializeWidgets();
    });
    // Prima della POST blocca ulteriori azioni sul form e segnala l’invio in corso.
    slot.addEventListener('htmx:beforeRequest', event => {
        if (!isPanelRequest(event) || event.detail.requestConfig.verb !== 'post') return;
        if (submitting || pending) { event.preventDefault(); return; }
        submitting = true;
        event.detail.elt.inert = true;
        slot.setAttribute('aria-busy', 'true');
        status.textContent = 'Invio della richiesta…';
        // Chiude la conferma di invio originale tramite l’istanza Bootstrap già attiva.
        const modal = slot.querySelector('.modal.show');
        if (modal) window.bootstrap?.Modal.getInstance(modal)?.hide();
    });
    // Accetta soltanto HTML marcato dalla view dell’assistente: login e pagine di errore restano fuori.
    slot.addEventListener('htmx:beforeSwap', event => {
        if (!isPanelRequest(event)) return;
        if (event.detail.xhr.getResponseHeader('X-Assistant-Form') !== 'ready') {
            event.detail.shouldSwap = false;
            status.textContent = event.detail.requestConfig.verb === 'post'
                ? 'Invio non completato. Controlla la sessione e riprova.'
                : 'Modulo non disponibile. Ricarica la pagina e riprova.';
        }
    });
    // Dopo l’aggiornamento distingue caricamento, invio riuscito e modulo con errori.
    slot.addEventListener('htmx:afterSwap', event => {
        if (!isPanelRequest(event)) return;
        const panel = prepareForm();
        if (!panel) return;
        if (pending && panel.dataset.ticketId === String(pending.id)) {
            // Aggiorna l’URL senza navigare: un refresh può riaprire la tipologia scelta.
            window.history.replaceState(null, '', panel.dataset.submitUrl + '#chatbot-request-panel');
            // Il coordinatore registra la selezione in chat soltanto dopo il caricamento riuscito.
            onSelected(pending);
            status.textContent = 'Modulo caricato.';
        } else if (panel.dataset.completed === 'true') {
            window.history.replaceState(null, '', panel.dataset.workspaceUrl);
            status.textContent = 'Richiesta inviata.';
        } else if (event.detail.requestConfig.verb === 'post') {
            status.textContent = 'Controlla i dati e gli errori indicati nel modulo.';
        }
        // workspace.js mostra i controlli e la vista divisa senza dipendere dai dettagli HTMX.
        slot.dispatchEvent(new CustomEvent('assistant:form-loaded', {bubbles: true}));
        panel.querySelector('#chatbot-form-title').focus({preventScroll: true});
    });
    // Ripristina l’interazione dopo la POST; in caso di errore HTTP il form corrente resta disponibile.
    slot.addEventListener('htmx:afterRequest', event => {
        if (!isPanelRequest(event) || event.detail.requestConfig.verb !== 'post') return;
        submitting = false;
        const form = slot.querySelector('form');
        if (form) form.inert = false;
        slot.setAttribute('aria-busy', 'false');
        if (event.detail.failed) status.textContent = 'Invio non riuscito. I dati restano nel modulo. Riprova.';
    });

    // Richiede conferma prima della GET e mantiene il modulo attuale se l’utente annulla.
    async function replaceForm(ticket) {
        pending = ticket;
        try {
            if (changes.hasChanges() && !await confirmFormReplacement()) {
                status.textContent = 'Cambio modulo annullato.';
                return;
            }
            // Se HTMX non è disponibile, usa la pagina completa dopo la stessa conferma.
            const url = new URL(window.htmx ? fragmentUrl : workspaceUrl, location.origin);
            url.searchParams.set('ticket_id', ticket.id);
            if (!window.htmx) { location.assign(url.href); return; }
            status.textContent = 'Caricamento del modulo…';
            slot.setAttribute('aria-busy', 'true');
            slot.setAttribute('hx-request', '{"timeout":15000}');
            // Evita nuove modifiche fra la conferma e l’arrivo del modulo sostitutivo.
            slot.inert = true;
            await window.htmx.ajax('GET', url.href, {source: slot, target: slot, swap: 'innerHTML'});
        } catch (_) {
            status.textContent = 'Caricamento non riuscito. Riprova.';
        } finally {
            // Il pannello torna utilizzabile anche se il caricamento fallisce o viene annullato.
            pending = null;
            slot.inert = false;
            slot.setAttribute('aria-busy', 'false');
        }
    }
    return {
        // true segnala alla chat che il clic è gestito dal pannello, senza navigazione del link.
        load(ticket) {
            if (pending || submitting) return true;
            const current = slot.querySelector('#chatbot-request-panel');
            // La stessa tipologia mantiene dati e posizione di scorrimento del form già aperto.
            if (current?.dataset.ticketId === String(ticket.id)) return true;
            replaceForm(ticket);
            return true;
        },
        // Interrompe una GET in corso quando viene azzerata la conversazione.
        cancel() {
            if (pending) window.htmx?.trigger(slot, 'htmx:abort');
        }
    };
}
