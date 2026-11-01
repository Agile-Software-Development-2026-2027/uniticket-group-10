/** Esegue la richiesta di ricerca e verifica il contratto JSON, senza gestire la vista. */
export async function searchTickets(url, query, csrfToken, signal) {
    // query è l’unico dato conversazionale inviato; signal permette timeout e annullamento.
    const response = await fetch(url, {
        method: 'POST',
        mode: 'same-origin',
        // Sessione sullo stesso dominio e token CSRF mantengono le protezioni Django.
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
        body: JSON.stringify({query}),
        signal
    });
    if (!response.ok) throw new Error('Ricerca non riuscita. Riprova o ricarica la pagina.');
    const data = await response.json();
    if (!data || typeof data !== 'object') throw new Error('Risposta API non valida.');
    // Sono ammesse risposte alternative: tickets[] oppure clarify con quick_replies.
    // Anche tickets: [] è valido; ogni tipologia deve avere ID numerico positivo e titolo testuale.
    const tickets = Array.isArray(data.tickets) && !('clarify' in data) && data.tickets.every(ticket =>
        ticket && Number.isSafeInteger(ticket.id) && ticket.id > 0 && typeof ticket.title === 'string');
    const clarify = !('tickets' in data) && typeof data.clarify === 'string' &&
        Array.isArray(data.quick_replies) && data.quick_replies.every(reply => typeof reply === 'string');
    // Una risposta incompatibile non viene inoltrata ai template Vue.
    if (!tickets && !clarify) throw new Error('Risposta API non valida.');
    return data;
}
