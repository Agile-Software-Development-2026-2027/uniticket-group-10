/* Page layout: pointer and keyboard resizing of the two panels. */
(() => {
    'use strict';
    const workspace = document.getElementById('chatbot-workspace');
    if (!workspace) return;
    const resizer = document.getElementById('chatbot-resizer');
    const controls = document.querySelector('.chatbot-layout-controls');
    function setView(view) {
        workspace.dataset.view = view;
        controls.querySelectorAll('[data-layout]').forEach(button => {
            button.setAttribute('aria-pressed', String(button.dataset.layout === view));
        });
    }
    if (controls) {
        controls.hidden = false;
        controls.addEventListener('click', event => {
            const button = event.target.closest('[data-layout]');
            if (button) setView(button.dataset.layout);
        });
        workspace.querySelectorAll('[data-show-panel]').forEach(link => {
            link.addEventListener('click', () => {
                if (workspace.dataset.view !== 'split') setView(link.dataset.showPanel);
            });
        });
    }
    if (!resizer) return;
    let share = 57;
    function resize(value) {
        share = Math.min(70, Math.max(35, value));
        workspace.style.setProperty('--chat-share', share + 'fr');
        workspace.style.setProperty('--draft-share', (100 - share) + 'fr');
        resizer.setAttribute('aria-valuenow', String(Math.round(share)));
    }
    resizer.setAttribute('aria-valuemin', '35');
    resizer.setAttribute('aria-valuemax', '70');
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
    resizer.addEventListener('keydown', event => {
        const values = {ArrowLeft: share - 2, ArrowRight: share + 2, Home: 35, End: 70, Enter: 57};
        if (!(event.key in values)) return;
        event.preventDefault();
        resize(values[event.key]);
    });
    resizer.addEventListener('dblclick', () => resize(57));
})();
