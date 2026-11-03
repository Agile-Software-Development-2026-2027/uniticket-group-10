export function createAgentClient(url, csrfToken) {
    return {
        sendMessage: (text, categoryId, signal) => sendToAgent(url, csrfToken, {
            type: 'message', message: text,
            ...(categoryId ? {category_id: categoryId} : {}),
        }, signal),
        selectForm: (categoryId, signal) => sendToAgent(url, csrfToken, {
            type: 'form_selected', category_id: categoryId,
        }, signal),
        requestFormHelp: (categoryId, signal) => sendToAgent(url, csrfToken, {
            type: 'request_form_help', category_id: categoryId,
        }, signal),
    };
}

// Unico punto di invio HTTP al proxy Django. Non modifica lo stato della chat.
async function sendToAgent(url, csrfToken, payload, signal) {
    const response = await fetch(new URL(url, window.location.href).href, {
        method: 'POST', credentials: 'same-origin', signal,
        headers: {'Content-Type': 'application/json', 'Accept': 'application/json', 'X-CSRFToken': csrfToken},
        body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error('Agent request failed');
    const result = await response.json();
    if (!Array.isArray(result?.messages)) throw new Error('Invalid agent response');
    return result;
}
