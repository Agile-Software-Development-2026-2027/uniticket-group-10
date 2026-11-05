import {AssistantRuntimeImpl, ExternalStoreRuntimeCore} from '@assistant-ui/core/internal';
import {RuntimeAdapter} from '@assistant-ui/core/store';
import {AuiConfig} from '@assistant-ui/vue';
import {computed, onMounted, onBeforeUnmount, ref, shallowRef} from 'vue';
import {useI18n} from '../i18n/index.js';
import {createAgentClient} from '../services/agent-client.js';

export function useTicketInteractions(root, csrfToken) {
    const {gettext} = useI18n();
    const client = createAgentClient(root.dataset.conversationUrl, csrfToken, () => threadId);
    const helpAction = shallowRef(null);
    const selectedCategory = ref(''), loadingCategory = ref(''), error = ref(''), failedRun = shallowRef(null);
    let disposed = false, active = null, generation = 0;
    let loadingRequest = null;
    let actions = Promise.resolve();
    let runDone = Promise.resolve();
    let messages = [];
    let suggestions = [];
    let threadId = crypto.randomUUID();
    const setMessages = value => {messages = value; sync();};
    const addMessage = message => setMessages([...messages, message]);

    const adapter = () => ({
        messages,
        suggestions,
        isRunning: !!active,
        adapters: {threadList: {threadId, onSwitchToNewThread: newChat}},
        convertMessage: message => ({id: message.id, role: message.role, content: message.content || '',
            metadata: {custom: message.metadata || {}}}),
        onNew: message => sendMessage(message.content.filter(part => part.type === 'text').map(part => part.text).join('')),
        onCancel: async () => cancelRequest(),
    });
    const core = new ExternalStoreRuntimeCore(adapter());
    const sync = () => core.setAdapter(adapter());
    const config = AuiConfig({threads: RuntimeAdapter(new AssistantRuntimeImpl(core))});

    function cancelRequest() {
        if (!active) return;
        active.cancelled = true;
        active.controller?.abort();
    }

    function handleRequestError(request) {
        if (disposed || request.generation !== generation) return;
        error.value = request.cancelled ? gettext('Risposta interrotta. Puoi riprovare.')
            : request.method === 'requestFormHelp' ? gettext('Non è stato possibile inviare la risposta. Riprova.')
                : gettext('La ricerca non è riuscita. Riprova tra poco.');
        failedRun.value = request;
    }

    function assistantMessage(message) {
        const tickets = message.content?.tickets;
        const prompts = message.suggestions;
        const action = message.action;
        if (typeof message.id !== 'string' || typeof message.message !== 'string' ||
            (message.content && (message.content.type !== 'tickets' || !Array.isArray(tickets) ||
                !tickets.every(ticket => typeof ticket.title === 'string' && Number.isInteger(ticket.category_id) &&
                    typeof ticket.url === 'string' && ticket.url.startsWith('/') && !ticket.url.startsWith('//')))) ||
            (action !== undefined && (action?.type !== 'request_form_help' ||
                !Number.isSafeInteger(action.category_id) || action.category_id <= 0 ||
                typeof action.label !== 'string' || !action.label.trim() || action.label.length > 500)) ||
            (prompts !== undefined && (!Array.isArray(prompts) ||
                !prompts.every(prompt => typeof prompt === 'string' && prompt.trim() && prompt.length <= 500)))) {
            throw new Error('Invalid assistant message');
        }
        return {id: message.id, role: 'assistant', content: message.message, metadata: {uniticket: {
            ...(tickets ? {tickets} : {}),
        }}};
    }

    function applyAgentResponse(result, request) {
        if (disposed || request.cancelled) return;
        const replies = result.messages.map(assistantMessage);
        if (request.generation === generation) {
            suggestions = (result.messages.at(-1)?.suggestions || []).map(prompt => ({prompt}));
            const action = result.messages.at(-1)?.action;
            helpAction.value = String(action?.category_id) === selectedCategory.value ? action : null;
        }
        setMessages([...messages, ...replies]);
    }

    async function executeRequest(request) {
        if (disposed || active) return;
        active = request;
        let resolveRun;
        runDone = new Promise(resolve => {resolveRun = resolve;});
        error.value = '';
        failedRun.value = null;
        suggestions = [];
        helpAction.value = null;
        sync();
        try {
            request.controller = new AbortController();
            const result = await client[request.method](...request.args, request.controller.signal);
            applyAgentResponse(result, request);
        } catch { handleRequestError(request); }
        finally {
            if (active === request) {
                active = null;
                sync();
            }
            resolveRun();
        }
    }

    function request(method, ...args) {
        return {method, args, generation, transcript: messages};
    }

    function newChat() {
        if (disposed) return;
        generation++;
        cancelRequest();
        active = null;
        actions = Promise.resolve();
        failedRun.value = null;
        error.value = '';
        helpAction.value = null;
        suggestions = [];
        messages = [];
        threadId = crypto.randomUUID();
        sync();
    }

    function sendMessage(text) {
        if (disposed || active || !text.trim()) return;
        addMessage({id: crypto.randomUUID(), role: 'user', content: text});
        return executeRequest(request('sendMessage', text, Number(selectedCategory.value) || undefined));
    }

    function requestFormHelp(action) {
        if (disposed || active || action !== helpAction.value ||
            !action || String(action.category_id) !== selectedCategory.value) return;
        addMessage({id: crypto.randomUUID(), role: 'user', content: action.label});
        return executeRequest(request('requestFormHelp', action.category_id));
    }

    function retryLastRequest() {
        const failed = failedRun.value;
        if (!failed || active || failed.generation !== generation) return;
        setMessages(failed.transcript);
        return executeRequest({...failed, cancelled: false});
    }

    function enqueueAction(method, ...args) {
        const category = selectedCategory.value, version = generation;
        const sending = actions.then(async () => {
            while (active) await runDone;
            if (disposed || version !== generation || category !== selectedCategory.value) return;
            await executeRequest(request(method, ...args));
        });
        actions = sending.catch(() => { if (!disposed) error.value = gettext('La ricerca non è riuscita. Riprova tra poco.'); });
        return sending;
    }

    function moduleLoaded(event) {
        const page = document.getElementById('assistant-page-content');
        if (event?.type === 'htmx:afterSwap' && event.detail.target !== page) return;
        const marker = page?.querySelector('[data-assistant-module]');
        const category = marker?.dataset.categoryId || '';
        const form = page?.querySelector('form[method="post"][enctype="multipart/form-data"]');
        if (form && marker?.dataset.url) form.action = marker.dataset.url;
        if (category === selectedCategory.value) return;
        generation++;
        failedRun.value = null;
        error.value = '';
        selectedCategory.value = category;
        suggestions = [];
        helpAction.value = null;
        sync();
        if (category) enqueueAction('selectForm', Number(category));
    }

    function ticketLoading(event) {
        if (event.detail.target?.id !== 'assistant-page-content') return;
        loadingRequest = event.detail.xhr;
        loadingCategory.value = event.detail.elt?.closest('a[data-ticket-id]')?.dataset.ticketId || '';
        // loadend also runs if HTMX cannot finish swapping the response.
        loadingRequest.addEventListener('loadend', () => ticketLoaded(event), {once: true});
    }
    function ticketLoaded(event) {
        if (disposed || !loadingRequest || event.detail.xhr !== loadingRequest) return;
        const failed = event.detail.failed || event.detail.error || loadingRequest.status === 0 || loadingRequest.status >= 400;
        loadingRequest = null;
        loadingCategory.value = '';
        if (failed) error.value = gettext('Il caricamento del modulo non è riuscito. Riprova.');
    }
    onMounted(() => {
        document.addEventListener('htmx:afterSwap', moduleLoaded);
        document.addEventListener('htmx:historyRestore', moduleLoaded);
        document.addEventListener('htmx:beforeSend', ticketLoading);
        document.addEventListener('htmx:afterRequest', ticketLoaded);
        document.addEventListener('htmx:onLoadError', ticketLoaded);
        moduleLoaded();
    });
    onBeforeUnmount(() => {
        disposed = true;
        cancelRequest();
        document.removeEventListener('htmx:afterSwap', moduleLoaded);
        document.removeEventListener('htmx:historyRestore', moduleLoaded);
        document.removeEventListener('htmx:beforeSend', ticketLoading);
        document.removeEventListener('htmx:afterRequest', ticketLoaded);
        document.removeEventListener('htmx:onLoadError', ticketLoaded);
    });
    return {config, helpAction, requestHelp: requestFormHelp,
        selectedCategory, loadingCategory, error,
        retry: retryLastRequest,
        failedSearch: computed(() => !!failedRun.value && failedRun.value.method === 'sendMessage'),
        canRetry: computed(() => !!failedRun.value && failedRun.value.generation === generation)};
}
