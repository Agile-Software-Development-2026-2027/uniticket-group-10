# Assistente: Vue nel browser, form Django

Le due demo (di Niccolò e Mirko) sono state convertite per usare **Vue 3, Axios e HTMX già inclusi in UniTicket**. Non servono nuove
librerie. Non è Vue SSR: Django genera
la pagina, Vue gestisce le interazioni nel browser.

Ricordati: Se ti ritrovi a scrivere (o generare) troppo JavaScript, forse stai complicando qualcosa che potrebbe essere gestito più semplicemente.

## TODO:
- Internazionalizzazione (i18n): Implementare il supporto multilingua. Per generare le traduzioni usa un LLM, non serve fare cose strane.
-Perfezionare l'implementazione attuale, migliorando la leggibilità, la manutenibilità e la semplicità del codice. **Evitare JavaScript non necessario quando Django o HTMX offrono già soluzioni adeguate.**
- Refactoring del retrieval service: Attualmente il servizio restituisce anche gli URL dei ticket, ma questa responsabilità non dovrebbe appartenergli. Pensa al retrival come un microservizio che conosce solo gli id.


## Pipeline in breve

1. **Apertura:** Django genera la pagina con il widget oppure il layout della
   demo `/assistant`. Vue monta la chat e recupera conversazione e bozza da
   `sessionStorage`. Aprire o chiudere il widget cambia solo la sua visibilità.
2. **Ricerca:** il messaggio passa da `chat.js` ad Axios, che invia
   `POST /api/search`. Il backend valida la richiesta e chiama `retrieval_service.search()`.
   I risultati contengono l’ID della categoria. Vue mostra i risultati.
3. **Clic su un risultato:** `selectTicket()` passa l’URL a `loadModule()` e poi
   ad `AssistantModules.load()`. HTMX esegue una GET direttamente alla vista
   originale UniTicket, che applica i suoi controlli e genera l’HTML del form.
4. **Aggiornamento del modulo:** il server restituisce l’HTML di una pagina
   UniTicket completa. Nel nostro `base.html` abbiamo racchiuso il contenuto
   centrale della pagina in un `<div id="assistant-page-content">`.
   `#assistant-page-content` è il selettore CSS che identifica quel div.
   HTMX cerca questo elemento **nell’HTML appena ricevuto** e prende ciò che
   contiene, senza inserire il resto della pagina, come head, menu e widget.

   Per esempio, se la risposta del server contiene:

   ```html
   <header>Menu del sito</header>
   <div id="assistant-page-content">
       <span hidden data-assistant-module="...">...</span>
       <form>Campi del modulo UniTicket...</form>
   </div>
   <div id="assistant-widget">Chat...</div>
   ```

   HTMX prende lo span e il form dentro quel div. Sostituisce quindi il contenuto
   di **un elemento già presente nella pagina aperta**: `assistant-page-content`
   nella demo widget, oppure `chatbot-request-content` nella demo pagina.
   Il div di destinazione resta al suo posto; cambiano soltanto i suoi contenuti.
   La chat è fuori dall’area sostituita, quindi resta montata e conserva
   conversazione, bozza e ricerca in corso. Infine, il caricatore imposta l’action
   del form sull’URL originale e Vue aggiorna la selezione.
5. **Invio del ticket:** il form esegue una normale POST multipart alla vista
   UniTicket. Validazione, allegati e creazione del ticket restano quelli originali.
   Questo invio ricarica la pagina: la chat viene ricreata e recupera lo stato salvato.
6. **Navigazione:** i cambi modulo gestiti dalle chat usano HTMX e la cronologia
   del browser. I link normali, il refresh e i redirect completi ricaricano la pagina;
   una ricerca ancora in corso può interrompersi. Il middleware traduce i redirect
   delle richieste HTMX in `HX-Redirect`, anche quando la sessione scade.

## Dove mettere le mani

| File | Responsabilità |
|---|---|
| `views/demo_page.py` | Vista GET del layout; indica solo l’URL iniziale per i segnalibri con categoria. |
| `middleware.py` | Converte i redirect delle viste originali in navigazioni complete per HTMX. |
| `templates/demo_page/partials/chatbot.html` | Template Vue della chat a pagina intera. |
| `templates/demo_widget/widget.html` | Template Vue del widget, risultati espandibili e comandi. |
| `templates/demo_page/workspace.html` | Layout affiancato e form originale Django. |
| `static/demo_page/js/app.js` | Stato delle viste, selezione della tipologia e divisore regolabile. |
| `static/demo_widget/js/app.js` | Apertura/chiusura, modalità mobile, focus e apertura dei moduli. |
| `static/assistant_shared/chat.js` | Ricerca REST, cronologia locale, errori, retry e scroll all’ultima domanda. |
| `static/assistant_shared/modules.js` | Collegamento tra Vue e HTMX per aggiornare i form Django. |

La pagina e il widget restano separati; condividono solo la logica comune.