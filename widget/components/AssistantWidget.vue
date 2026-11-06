<script setup>
import {useI18n} from '../i18n/index.js';
import {AuiIf, ThreadPrimitiveRoot, ThreadPrimitiveViewport, ThreadPrimitiveMessages,
    ThreadPrimitiveScrollToBottom, ComposerPrimitiveInput, ComposerPrimitiveSend, ComposerPrimitiveCancel,
    ThreadPrimitiveSuggestions, SuggestionPrimitiveTrigger, SuggestionPrimitiveTitle, ThreadListPrimitiveNew, useAuiState} from '@assistant-ui/vue';
import {nextTick, onBeforeUnmount, ref, watch} from 'vue';
import Message from './Message.vue';

const props = defineProps({interactions: {type: Object, required: true}, root: {type: Object, required: true}});
const {helpAction, requestHelp, selectedCategory, loadingCategory, error, retry, failedSearch, canRetry} = props.interactions;
const running = useAuiState(state => state.thread.isRunning);
const {gettext} = useI18n();
const panel = ref(null);
const open = ref(false);

watch(open, value => props.root.classList.toggle('assistant-widget--open', value));
function toggle() {
    stopPanelResize();
    open.value = !open.value;
    nextTick(() => props.root.querySelector(open.value ? 'textarea' : '.assistant-launcher')?.focus());
}

// Puoi ignorare sta roba, serve solo per il resizing
const MIN_SIZE = 320;
const MIN_MARGIN = 16;
const KEYBOARD_STEP = 20;
const MOBILE_QUERY = '(max-width: 576px)';
const clampSize = (size, available) => Math.min(Math.max(0, available), Math.max(MIN_SIZE, size));

let resizing = null;
const isMobile = () => window.matchMedia(MOBILE_QUERY).matches;

function setPanelSize(width, height) {
    const element = panel.value;
    if (!element || isMobile()) return;
    const bounds = element.getBoundingClientRect();
    const margin = Math.max(MIN_MARGIN, window.innerWidth - bounds.right);
    const maxWidth = bounds.right - margin;
    const maxHeight = bounds.bottom - margin;
    element.style.setProperty('--assistant-panel-width', clampSize(width, maxWidth) + 'px');
    element.style.setProperty('--assistant-panel-height', clampSize(height, maxHeight) + 'px');
}

function startPanelResize(event) {
    if (resizing || event.isPrimary === false || event.button !== 0 || isMobile() || !panel.value) return;
    event.preventDefault();
    const bounds = panel.value.getBoundingClientRect();
    const handle = event.currentTarget;
    handle.focus({preventScroll: true});
    handle.setPointerCapture(event.pointerId);
    resizing = {handle, pointerId: event.pointerId, x: event.clientX, y: event.clientY,
        width: bounds.width, height: bounds.height};
}

function resizePanel(event) {
    if (!resizing || resizing.pointerId !== event.pointerId) return;
    setPanelSize(resizing.width + resizing.x - event.clientX, resizing.height + resizing.y - event.clientY);
}

function stopPanelResize(event) {
    const start = resizing;
    if (!start || (event && start.pointerId !== event.pointerId)) return;
    resizing = null;
    if (start.handle.hasPointerCapture(start.pointerId)) start.handle.releasePointerCapture(start.pointerId);
}

function resizePanelWithKeyboard(event) {
    if (!panel.value || isMobile()) return;
    const delta = {ArrowLeft: [KEYBOARD_STEP, 0], ArrowRight: [-KEYBOARD_STEP, 0],
        ArrowUp: [0, KEYBOARD_STEP], ArrowDown: [0, -KEYBOARD_STEP]}[event.key];
    if (!delta) return;
    event.preventDefault();
    const bounds = panel.value.getBoundingClientRect();
    setPanelSize(bounds.width + delta[0], bounds.height + delta[1]);
}

onBeforeUnmount(() => stopPanelResize());
</script>

<template>
    <transition name="assistant-panel">
    <section ref="panel" id="assistant-panel" class="assistant-panel" v-show="open" :inert="!open" :aria-hidden="!open"
             role="region" aria-labelledby="assistant-title" @keydown.esc.prevent="open && toggle()">
        <button type="button" class="assistant-resize" aria-controls="assistant-panel"
                :aria-label="gettext('Ridimensiona la chat')" :title="gettext('Trascina o usa i tasti freccia per ridimensionare')"
                aria-keyshortcuts="ArrowUp ArrowDown ArrowLeft ArrowRight"
                @pointerdown="startPanelResize" @pointermove="resizePanel" @pointerup="stopPanelResize"
                @pointercancel="stopPanelResize" @lostpointercapture="stopPanelResize" @keydown="resizePanelWithKeyboard">
        </button>
        <header class="assistant-header">
            <h2 id="assistant-title">{{ gettext('Assistente UniTicket') }}</h2>
            <div class="assistant-header-actions">
                <ThreadListPrimitiveNew class="assistant-header-button" data-testid="assistant-new-chat"
                    :title="gettext('Nuova chat')" :aria-label="gettext('Nuova chat')"
                    @click="$nextTick(() => root.querySelector('textarea')?.focus())">
                    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7M16 3l5 5M10 14l4-1 8-8-3-3-8 8-1 4Z"/></svg>
                </ThreadListPrimitiveNew>
                <button type="button" class="assistant-header-button" data-testid="assistant-close" @click="toggle"
                    :aria-label="gettext('Chiudi l\'assistente')">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M6 18 18 6"/></svg>
                </button>
            </div>
        </header>
        <thread-primitive-root class="assistant-thread" data-testid="assistant-chat-view">
            <thread-primitive-viewport class="assistant-messages" role="log" :aria-label="gettext('Assistente')">
                <aui-if :condition="state => state.thread.messages.length === 0">
                    <div class="assistant-msg assistant-msg--assistant" data-testid="assistant-welcome">
                        <span class="assistant-author">{{ gettext('Assistente') }}</span>
                        <p>{{ gettext('Ciao! Descrivi ciò di cui hai bisogno e ti suggerirò la richiesta più adatta. Ad esempio: "Ho bisogno di un certificato di iscrizione"') }}</p>
                    </div>
                </aui-if>
                <thread-primitive-messages>
                    <Message :selected-category="selectedCategory" :loading-category="loadingCategory" />
                </thread-primitive-messages>
                <div v-if="helpAction" class="assistant-suggestions" role="group" :aria-label="gettext('Aiuto alla compilazione')">
                    <button type="button" class="assistant-suggestion" data-testid="assistant-form-help"
                            :disabled="running" @click="requestHelp(helpAction)" v-text="helpAction.label"></button>
                </div>
                <aui-if :condition="state => !state.thread.isRunning && state.suggestions.suggestions.length > 0">
                    <div class="assistant-suggestions" role="group" :aria-label="gettext('Aiuto alla compilazione')">
                        <ThreadPrimitiveSuggestions>
                            <SuggestionPrimitiveTrigger send class="assistant-suggestion">
                                <SuggestionPrimitiveTitle />
                            </SuggestionPrimitiveTrigger>
                        </ThreadPrimitiveSuggestions>
                    </div>
                </aui-if>
                <div v-if="error && canRetry" class="assistant-msg assistant-msg--assistant">
                    <span class="assistant-author">{{ gettext('Assistente') }}</span>
                    <p class="assistant-error" role="alert" v-text="error"></p>
                    <button type="button" class="assistant-retry" :disabled="running" @click="retry"><span v-if="failedSearch">{{ gettext('Riprova la ricerca') }}</span><span v-else>{{ gettext('Riprova') }}</span></button>
                </div>
                <thread-primitive-scroll-to-bottom class="assistant-jump" :aria-label="gettext('Vai agli ultimi messaggi')">
                    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>
                </thread-primitive-scroll-to-bottom>
            </thread-primitive-viewport>
        </thread-primitive-root>
        <p v-if="error && !canRetry" class="assistant-status assistant-error" role="alert" v-text="error"></p>
        <div class="assistant-form">
            <div class="assistant-compose">
                <composer-primitive-input rows="1" maxlength="500" :placeholder="gettext('Scrivi la tua richiesta…')"
                    :aria-label="gettext('Scrivi la tua richiesta…')"></composer-primitive-input>
                <composer-primitive-cancel v-if="running" class="assistant-send" data-testid="assistant-chat-stop"
                    :aria-label="gettext('Interrompi')">
                    <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="1"/></svg>
                </composer-primitive-cancel>
                <!-- Invia tramite composer.send(), che richiama onNew nel runtime. -->
                <composer-primitive-send v-else class="assistant-send" data-testid="assistant-chat-send"
                    :aria-label="gettext('Invia')">
                    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 7-7 7 7M12 5v14"/></svg>
                </composer-primitive-send>
            </div>
        </div>
    </section>
    </transition>
    <button type="button" class="assistant-launcher" aria-controls="assistant-panel" :aria-expanded="open" @click="toggle">
        <span class="assistant-launcher-icon" aria-hidden="true">
        <svg class="assistant-launcher-chat" viewBox="0 0 24 24"><path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8A8.5 8.5 0 0 1 8.7 3.9a8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8v.5Z"/><path d="M8 10h8M8 14h5"/></svg>
        <svg class="assistant-launcher-close" viewBox="0 0 24 24"><path d="m6 6 12 12M6 18 18 6"/></svg>
        </span>
        <span>{{ gettext('Assistente') }}</span>
    </button>
</template>
