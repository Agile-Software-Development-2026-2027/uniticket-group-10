/* HTMX aggiorna il modulo Django; Vue mantiene lo stato della chat senza ricaricare la pagina. */
window.AssistantModules = function (targetId, sourceId = targetId) {
    // Il contatore identifica il caricamento corrente e rende obsolete le risposte precedenti.
    let serial = 0;
    return {
        cancel() { serial++; htmx.trigger(document.getElementById(targetId), 'htmx:abort'); },
        async load(url, push = true) {
            this.cancel();
            const request = serial;
            const target = document.getElementById(targetId);
            let failed = false, redirected = false;
            // Considera solo gli eventi del contenitore richiesto, ignorando quelli dei suoi figli.
            const completed = event => {
                if (event.detail.elt !== target) return;
                failed = event.detail.failed;
                redirected = Boolean(event.detail.xhr.getResponseHeader('HX-Redirect'));
            };
            target.addEventListener('htmx:afterRequest', completed);
            try {
                // Estrae dalla risposta solo i figli del contenitore, lasciando montata la chat Vue.
                await htmx.ajax('GET', url, {source: target, target,
                    select: '#' + sourceId + ' > *', swap: 'innerHTML show:none'});
                // Con HX-Redirect la navigazione è gestita da HTMX; le richieste superate si ignorano.
                if (request !== serial || redirected) return null;
                if (failed) throw new Error('Impossibile caricare il modulo');
                const state = target.querySelector('[data-assistant-module]')?.dataset;
                if (!state) throw new Error('Modulo non disponibile');
                // I ripristini con Indietro/Avanti non devono aggiungere nuove voci alla cronologia.
                // La demo pagina mantiene il proprio URL: la POST deve comunque raggiungere UniTicket.
                const form = target.querySelector('form[method="post"][enctype="multipart/form-data"]');
                if (form) form.action = state.url;
                if (push) window.history.pushState(null, '', state.url);
                // Evita invii involontari del modulo premendo Invio in un campo di testo.
                target.onkeydown = event => {
                    if (event.key === 'Enter' && event.target.matches('form input')) event.preventDefault();
                };
                // Alla conferma nella modale, nascondila insieme allo sfondo oscurato.
                target.onclick = event => {
                    const submit = event.target.closest('.modal [type="submit"]');
                    if (!submit) return;
                    submit.closest('.modal').classList.remove('show');
                    document.querySelectorAll('.modal-backdrop.fade').forEach(backdrop => { backdrop.style.opacity = '0'; });
                };
                // Inizializza il ridimensionamento delle textarea appena inserite da HTMX.
                if (window.autogrow) target.querySelectorAll('textarea').forEach(window.autogrow);
                return {categoryId: state.categoryId, hasModule: state.hasModule === 'true', url: state.url};
            } catch (error) {
                if (request !== serial) return null;
                throw error;
            } finally { target.removeEventListener('htmx:afterRequest', completed); }
        },
    };
};
