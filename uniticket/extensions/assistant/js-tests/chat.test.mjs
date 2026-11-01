import test from 'node:test';
import assert from 'node:assert/strict';
import {createChatHistory} from '../static/chat/chat-history.js';
import {searchTickets} from '../static/chat/chat-api.js';

// Storage simulato: i test non accedono ai dati reali del browser.
function storage() {
    const items = new Map();
    return {getItem: key => items.get(key) ?? null, setItem: (key, value) => items.set(key, value),
        removeItem: key => items.delete(key)};
}

// Verifica la migrazione delle vecchie selezioni e impedisce duplicati al ripristino.
test('old history survives Vue migration, including neutral selections and replies', () => {
    const memory = storage();
    memory.setItem('chat', JSON.stringify({history: [{author: 'Tu', text: 'query'},
        {author: 'Assistente', text: 'reply'}, {author: 'Tu', text: 'Ho selezionato: Certificato'}],
        selectedId: 316, lastResponse: {tickets: [{id: 316, title: 'Certificato'}]}}));
    const history = createChatHistory('chat', [], memory);
    assert.deepEqual(history.messages.at(-1), {author: 'selection', text: 'Certificato'});
    assert.equal(history.lastResponse.tickets.length, 1);
    history.select('316', 'Certificato');
    assert.equal(history.messages.length, 3);
});

// Controlla limite di 50 eventi, ripristino, separazione per utente e reset.
test('history is bounded, persists after reload and resets independently for each user', () => {
    const memory = storage();
    const history = createChatHistory('user-1', [], memory);
    for (let i = 0; i < 60; i++) history.append('Tu', String(i));
    assert.equal(createChatHistory('user-1', [], memory).messages.length, 50);
    assert.equal(createChatHistory('user-2', [], memory).messages.length, 0);
    history.clear();
    assert.equal(createChatHistory('user-1', [], memory).messages.length, 0);
});

// La conversazione deve continuare anche quando il browser non consente lo storage.
test('storage errors do not prevent an in-memory conversation', () => {
    const denied = {getItem() { throw new Error(); }, setItem() { throw new Error(); }, removeItem() { throw new Error(); }};
    const history = createChatHistory('chat', ['old query'], denied);
    history.append('Assistente', 'reply');
    assert.equal(history.messages.length, 2);
    history.clear();
    assert.equal(history.messages.length, 0);
});

// fetch è simulata: vengono verificati payload, CSRF e risposte senza chiamare il server.
test('API client preserves JSON query, CSRF, and both response branches', async context => {
    const responses = [{tickets: [{id: 316, title: 'Certificato'}]}, {tickets: []},
        {clarify: 'Dipartimento?', quick_replies: ['DeMaCS']}];
    let sent;
    context.mock.method(globalThis, 'fetch', async (url, options) => {
        sent = {url, ...options};
        return {ok: true, json: async () => responses.shift()};
    });
    assert.equal((await searchTickets('/api/search', 'test', 'token')).tickets.length, 1);
    assert.equal(sent.url, '/api/search');
    assert.equal(sent.headers['X-CSRFToken'], 'token');
    assert.deepEqual(JSON.parse(sent.body), {query: 'test'});
    assert.deepEqual(await searchTickets('/api/search', 'test', 'token'), {tickets: []});
    assert.deepEqual((await searchTickets('/api/search', 'test', 'token')).quick_replies, ['DeMaCS']);
});

// Dati incompatibili ed errori HTTP devono essere intercettati prima dell’aggiornamento della vista.
test('API client rejects malformed responses and failed HTTP requests', async context => {
    const mock = context.mock.method(globalThis, 'fetch', async () => ({ok: true,
        json: async () => ({tickets: [{id: 'wrong', title: 'title'}]})}));
    await assert.rejects(searchTickets('/', 'test', 'token'), /non valida/);
    mock.mock.mockImplementation(async () => ({ok: false}));
    await assert.rejects(searchTickets('/', 'test', 'token'), /non riuscita/);
});
