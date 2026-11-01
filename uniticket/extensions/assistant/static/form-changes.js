/** Rileva modifiche non salvate confrontando i valori attuali con quelli del modulo caricato. */
export function createFormChanges(form, {initiallyDirty = false} = {}) {
    // FormData considera i campi inviabili, comprese selezioni multiple e checkbox selezionate.
    function snapshot() {
        if (!form) return '[]';
        const values = [...new FormData(form)]
            // Il token CSRF può cambiare senza rappresentare una modifica ai dati dell’utente.
            .filter(([name]) => name !== 'csrfmiddlewaretoken')
            // Per gli allegati vengono confrontati i metadati, senza leggere il contenuto del file.
            .map(([name, value]) => [name, typeof value === 'string' ? value : {
                name: value.name, size: value.size, type: value.type,
                // Il browser genera una data anche per file vuoti: normalizzarla evita falsi avvisi.
                lastModified: value.name ? value.lastModified : 0
            }]);
        return JSON.stringify(values);
    }
    // La fotografia iniziale è privata; ripristinare gli stessi valori elimina l’avviso.
    const initial = snapshot();
    // Dopo una risposta con errori, initiallyDirty mantiene la protezione dei dati ancora non salvati.
    return {hasChanges: () => initiallyDirty || snapshot() !== initial};
}
