/* Widget assistente: apre/chiude la chat, chiama /api/search e mostra le categorie. */
(() => {
    'use strict';
    const widget = document.getElementById('assistant-widget'); /*cerca nella pagina l'elemento con */
    /*id="assistant-widget" ovvero il <div> che contiene tutto il widget */

    if (!widget) return;

    const launcher = widget.querySelector('.assistant-launcher'); /* bolla in basso a destra */
    const panel = widget.querySelector('.assistant-panel'); /* finestra */
    const messages = widget.querySelector('.assistant-messages'); /* area dei messaggi */
    const form = widget.querySelector('.assistant-form'); /* form in basso */
    const input = form.querySelector('textarea'); /* casella di testo in basso */
    const sendButton = form.querySelector('button'); /* bottone di invio in basso */
    const csrfToken = form.querySelector('[name="csrfmiddlewaretoken"]').value; /* prende il token CSRF e lo inserisce in un campo nascosto */
    /*da cui ne può leggere poi il valore*/
    const storageKey = widget.dataset.storageKey; /* legge l'attributo data-storage-key del widget */
    /* data-storage-key diventa dataset.storageKey->nome con cui la conversazione viene salvata nel browser, contiene l'ID dell'utente */
    const welcome = {author: 'bot', text: 'Ciao! Descrivi cosa ti serve e ti suggerisco la richiesta giusta.'};
    let history = []; /* cronologia conversazione */
    // ogni messaggio del tipo [
    // {author: 'bot', text: 'Ciao! Descrivi cosa ti serve....'}
    // {author: 'user', text: 'Ho bisogno di un certificato di iscrizione'}
    // ]


    function save() {  // salva la conversazione
        try { //sessionStorage è la memoria del browser, sopravvive al cambio di scheda, muore quando la chiudi
            sessionStorage.setItem(storageKey, JSON.stringify({history, open: !panel.hidden}));
            // vengono salvati la cronologia e lo stato del widget (aperto/chiuso)
            // stringify serve per convertire l'oggetto in una stringa JSON, perché sessionStorage può salvare solo stringhe
        } catch (_) { /* senza storage la chat funziona lo stesso ma non viene ricordata */ }
    }

    function load() { // fa l'opposto di save, converte il testo da sessionStorage in oggetto JS
        try {
            return JSON.parse(sessionStorage.getItem(storageKey)) || {};
        } catch (_) {
            return {};
        }
    }

    // javascript tiene i messaggi come dati nel formato sotto desccritto
    // {author: 'bot', text: 'Ecco le richieste…', replies: [ {...}, {...} ]}
    // render conferte questo in html e lo mostra nella finestra del widget
    // ESEMPIO: {
    /*      author: 'bot',
            text: 'Ecco le richieste che potrebbero fare al caso tuo:',
            replies: [
                {type: 'ticket', title: 'Richiesta certificato di laurea', ticket_id: 318},
               {type: 'ticket', title: 'Richiesta Certificato di Iscrizione', ticket_id: 316}
            ]
        }               */  
    //DIVENTA: 
    /*
    <div class="assistant-msg assistant-msg--bot">
        <p>Ecco le richieste che potrebbero fare al caso tuo:</p>
        <a class="assistant-card" href="/assistant/open?ticket_id=318">Richiesta certificato di laurea</a>
        <a class="assistant-card" href="/assistant/open?ticket_id=316">Richiesta Certificato di Iscrizione</a>
    </div>
    */
    function render(entry) {
        const bubble = document.createElement('div');
        bubble.className = 'assistant-msg assistant-msg--' + entry.author;
        // crea un div con classi assistant-msg e assistant-msg--bot o assistant-msg--user a seconda dell'autore
        const text = document.createElement('p');
        text.textContent = entry.text;
        bubble.append(text); //crea un p con il testo del messaggio e lo aggiunge al div
        // per ogni categoria crea un link (<a>) con il titolo della categoria e l'URL per aprire la richiesta
        for (const reply of entry.replies || []) {
            if (reply.type !== 'ticket') continue;   // per ora gestiamo solo le categorie
            const card = document.createElement('a');
            card.className = 'assistant-card';
            card.href = widget.dataset.openUrl + '?ticket_id=' + encodeURIComponent(reply.ticket_id);
            card.textContent = reply.title;
            bubble.append(card);
        }
        messages.append(bubble);
        messages.scrollTop = messages.scrollHeight;
    }

    function add(entry) {
        history.push(entry);
        render(entry);
        save();
    }

    function setOpen(open) { //apre o chiude finestra del widget
        panel.hidden = !open;
        launcher.setAttribute('aria-expanded', String(open));
        if (open) input.focus();
        save();
    }

    function reset() { // nuova conversazione, cancella cronologia e messaggi
        history = [];
        messages.replaceChildren();
        add(welcome);
    }

    async function search(query) { // async, dentro si puo aspettare una risposta dal server senza bloccare il browser
        add({author: 'user', text: query}); // aggiunge il messaggio dell'utente alla cronologia e lo mostra
        const typing = document.createElement('p'); 
        typing.className = 'assistant-typing';
        typing.textContent = 'Sto cercando…';
        messages.append(typing);
        sendButton.disabled = true;
        try {
            const response = await fetch(widget.dataset.searchUrl, { //chiamata all'API /api/search, widget.dataset.searchUrl contiene l'URL dell'API
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
                body: JSON.stringify({query}),
            });
            if (response.status === 401 || response.status === 403) {
                throw new Error('La sessione è scaduta: ricarica la pagina e accedi di nuovo.');
            }
            if (!response.ok) throw new Error('Qualcosa è andato storto. Riprova.');
            const data = await response.json();
            const replies = Array.isArray(data.replies) ? data.replies : [];
            add({
                author: 'bot',
                text: replies.length ? 'Ecco le richieste che potrebbero fare al caso tuo:'
                                     : 'Non ho trovato richieste adatte. Prova a riformulare.',
                replies,
            });
        } catch (error) {
            add({author: 'bot', text: error.name === 'TypeError'
                ? 'Impossibile contattare il server. Riprova.' : error.message});
        } finally {
            typing.remove();
            sendButton.disabled = false;
            input.focus();
        }
    }

    launcher.addEventListener('click', () => setOpen(panel.hidden));
    widget.querySelector('.assistant-close').addEventListener('click', () => setOpen(false));
    widget.querySelector('.assistant-reset').addEventListener('click', reset);
    // listener sulla bolla in basso a destra, quando viene cliccata apre o chiude il widget

    form.addEventListener('submit', event => {
        event.preventDefault();                     // niente ricaricamento della pagina
        const query = input.value.trim();
        if (!query || sendButton.disabled) return;
        input.value = '';
        search(query);
    }); // listener sul form, quando viene inviato chiama la funzione search con il testo della casella di input
    input.addEventListener('keydown', event => {   // Invio invia, Maiusc+Invio va a capo
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            form.requestSubmit();
        }
    });

    // Il bottone "Assistente" della navbar apre il widget invece di cambiare pagina.
    // Questo permette di aprire il widget anche da altre pagine dell'applicazione.
    document.addEventListener('click', event => {
        const link = event.target.closest('[data-assistant-open]');
        if (!link) return;
        event.preventDefault();
        setOpen(true);
    });

    // quando la pagina è pronta:
    const saved = load(); // carica quello che era salvato
    history = Array.isArray(saved.history) ? saved.history : []; // se c'è una cronologia la carica, altrimenti history rimane vuota
    if (history.length) history.forEach(render); else add(welcome); // se c'è una cronologia la mostra, altrimenti mostra il messaggio di benvenuto
    if (saved.open) setOpen(true); // se il widget era aperto lo riapre, altrimenti rimane chiuso
})();
