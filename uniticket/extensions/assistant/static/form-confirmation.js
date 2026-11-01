/** Mostra il dialogo HTML di sostituzione e restituisce soltanto l’esito della scelta. */
export function confirmFormReplacement() {
    const dialog = document.getElementById('chatbot-replace-confirmation');
    // Il chiamante attende la scelta prima di richiedere il nuovo modulo.
    return new Promise(resolve => {
        // Annulla ed Escape non autorizzano la sostituzione; soltanto il valore replace la conferma.
        dialog.returnValue = 'cancel';
        // once evita di accumulare listener quando il dialogo viene riaperto.
        dialog.addEventListener('close', () => resolve(dialog.returnValue === 'replace'), {once: true});
        // La modalità modale impedisce interazioni con i pannelli durante la scelta.
        dialog.showModal();
    });
}
