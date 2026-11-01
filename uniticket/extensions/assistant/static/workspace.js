/* Gestisce disposizione e dimensioni dei pannelli, senza intervenire su ricerca o salvataggio. */
(() => {
    'use strict';
    const workspace = document.getElementById('chatbot-workspace');
    if (!workspace) return;
    const resizer = document.getElementById('chatbot-resizer');
    const controls = document.querySelector('.chatbot-layout-controls');
    // Assegna ai due pannelli la stessa altezza nella sola vista divisa.
    function fitSplitPanels() {
        if (workspace.dataset.view !== 'split') return;
        // Usa l’85% della finestra, con limiti di 640–900 px per mantenere uno spazio utilizzabile.
        const height = Math.max(640, Math.min(900, Math.round(window.innerHeight * 0.85)));
        workspace.style.setProperty('--split-height', height + 'px');
    }
    window.addEventListener('resize', fitSplitPanels);
    window.addEventListener('load', fitSplitPanels);
    // Attende il primo calcolo del layout prima di impostare l’altezza iniziale.
    requestAnimationFrame(fitSplitPanels);
    // data-view attiva le regole CSS per chat, modulo o vista affiancata.
    function setView(view) {
        workspace.dataset.view = view;
        fitSplitPanels();
        controls.querySelectorAll('[data-layout]').forEach(button => {
            button.setAttribute('aria-pressed', String(button.dataset.layout === view));
        });
    }
    if (controls) {
        // I comandi di ampliamento servono solo dopo l’apertura di un modulo.
        controls.hidden = !document.getElementById('chatbot-request-panel');
        controls.addEventListener('click', event => {
            const button = event.target.closest('[data-layout]');
            if (button) setView(button.dataset.layout);
        });
        // La delega sul contenitore stabile comprende anche i link arrivati tramite HTMX.
        workspace.addEventListener('click', event => {
            const link = event.target.closest('[data-show-panel]');
            if (link && workspace.dataset.view !== 'split') setView(link.dataset.showPanel);
        });
        // Il pannello comunica il caricamento con un evento, senza conoscere la gestione del layout.
        workspace.addEventListener('assistant:form-loaded', () => {
            controls.hidden = false;
            workspace.classList.remove('chatbot-workspace--chat-only');
            workspace.querySelector('[data-form-link]').hidden = false;
            setView('split');
        });
    }
    if (!resizer) return;
    let share = 57;
    // La quota della chat resta fra 35% e 70%; la parte restante viene assegnata al modulo.
    function resize(value) {
        share = Math.min(70, Math.max(35, value));
        workspace.style.setProperty('--chat-share', share + 'fr');
        workspace.style.setProperty('--draft-share', (100 - share) + 'fr');
        resizer.setAttribute('aria-valuenow', String(Math.round(share)));
    }
    resizer.setAttribute('aria-valuemin', '35');
    resizer.setAttribute('aria-valuemax', '70');
    // La cattura del puntatore mantiene il trascinamento anche fuori dalla barra.
    resizer.addEventListener('pointerdown', event => {
        if (event.button !== 0) return;
        event.preventDefault();
        resizer.setPointerCapture(event.pointerId);
    });
    resizer.addEventListener('pointermove', event => {
        if (!resizer.hasPointerCapture(event.pointerId)) return;
        const bounds = workspace.getBoundingClientRect();
        resize(100 * (event.clientX - bounds.left) / bounds.width);
    });
    for (const type of ['pointerup', 'pointercancel']) resizer.addEventListener(type, event => {
        if (resizer.hasPointerCapture(event.pointerId)) resizer.releasePointerCapture(event.pointerId);
    });
    // Frecce, Home, End e Invio rendono il separatore utilizzabile anche da tastiera.
    resizer.addEventListener('keydown', event => {
        const values = {ArrowLeft: share - 2, ArrowRight: share + 2, Home: 35, End: 70, Enter: 57};
        if (!(event.key in values)) return;
        event.preventDefault();
        resize(values[event.key]);
    });
    // Il doppio clic ripristina la proporzione iniziale fra i pannelli.
    resizer.addEventListener('dblclick', () => resize(57));
})();
