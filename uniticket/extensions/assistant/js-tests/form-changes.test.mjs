import test from 'node:test';
import assert from 'node:assert/strict';
import {createFormChanges} from '../static/form-changes.js';

// Simula le coppie prodotte da FormData, compresi più valori per lo stesso campo.
globalThis.FormData = class {
    constructor(form) { return form.entries()[Symbol.iterator](); }
};

// Il ripristino del valore iniziale annulla la modifica; la rotazione del CSRF non genera avvisi.
test('text edits and restoring original values', () => {
    let values = [['subject', 'Originale'], ['csrfmiddlewaretoken', 'a']];
    const changes = createFormChanges({entries: () => values});
    assert.equal(changes.hasChanges(), false);
    values = [['subject', 'Modificato'], ['csrfmiddlewaretoken', 'a']];
    assert.equal(changes.hasChanges(), true);
    values = [['subject', 'Originale'], ['csrfmiddlewaretoken', 'b']];
    assert.equal(changes.hasChanges(), false);
});

// Aggiunte, rimozioni e selezioni differenti devono essere riconosciute, anche senza modulo attivo.
test('checkboxes, multiple selections and no active form', () => {
    let values = [['department', 'DeMaCS'], ['options', 'one']];
    const changes = createFormChanges({entries: () => values});
    values.push(['options', 'two']);
    assert.equal(changes.hasChanges(), true);
    values.pop();
    assert.equal(changes.hasChanges(), false);
    values = [['department', 'DiMeS'], ['options', 'one']];
    assert.equal(changes.hasChanges(), true);
    assert.equal(createFormChanges(null).hasChanges(), false);
});

// Gli allegati vuoti non devono risultare modificati solo per il timestamp generato dal browser.
test('empty file timestamps do not cause false warnings; selected files do', () => {
    let clock = 1;
    let file = null;
    const changes = createFormChanges({entries: () => [['attachment', file || {
        name: '', size: 0, type: 'application/octet-stream', lastModified: clock++
    }]]});
    assert.equal(changes.hasChanges(), false);
    file = {name: 'demo.txt', size: 4, type: 'text/plain', lastModified: 100};
    assert.equal(changes.hasChanges(), true);
    file = null;
    assert.equal(changes.hasChanges(), false);
});

// Dopo errori di validazione i dati rimangono non salvati, anche se coincidono con il form restituito.
test('invalid submitted data remain unsaved after the error response', () => {
    const form = {entries: () => [['subject', 'Bozza']]};
    assert.equal(createFormChanges(form, {initiallyDirty: true}).hasChanges(), true);
});
