<script setup>
import {useI18n} from '../../i18n/index.js';
import {useAuiState} from '@assistant-ui/vue';
import {onMounted, ref} from 'vue';
defineProps({ticket: {type: Object, required: true}, selectedCategory: String, loadingCategory: String});
const {gettext} = useI18n();
const running = useAuiState(state => state.thread.isRunning);
const link = ref(null);
// Reprocessing on updates would reset HTMX's counters during an active request.
onMounted(() => window.htmx?.process(link.value));
</script>

<template>
        <li>
            <a ref="link" class="assistant-card" :class="{'assistant-card--opened': String(ticket.category_id) === selectedCategory}"
               hx-boost="true" hx-target="#assistant-page-content" hx-select="#assistant-page-content > *"
               hx-ext="ticket-form" hx-swap="ticket-form show:none" hx-sync="#assistant-root:replace"
               :href="ticket.url" :data-ticket-id="ticket.category_id" :data-structure-name="ticket.structure_name"
               :aria-current="String(ticket.category_id) === selectedCategory ? 'page' : null"
               :aria-busy="String(ticket.category_id) === loadingCategory"
               :aria-disabled="running || String(ticket.category_id) === selectedCategory"
               @click="(running || String(ticket.category_id) === selectedCategory) && $event.preventDefault()">
                <span class="assistant-card-details">
                    <span class="assistant-card-title" v-text="ticket.title"></span>
                    <small v-if="ticket.structure_name" class="assistant-card-structure" v-text="ticket.structure_name"></small>
                    <small v-if="String(ticket.category_id) === loadingCategory" class="assistant-opened-label" role="status">{{ gettext('Caricamento modulo…') }}</small>
                    <small v-else-if="String(ticket.category_id) === selectedCategory" class="assistant-opened-label">{{ gettext('Modulo aperto') }}</small>
                </span>
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14m-6-6 6 6-6 6"/></svg>
            </a>
        </li>
</template>
