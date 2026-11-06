<script setup>
import {useI18n} from '../i18n/index.js';
import {MessagePrimitiveParts, MessagePrimitiveRoot, useAuiState} from '@assistant-ui/vue';
import TicketResults from './ticket/TicketResults.vue';

defineProps({selectedCategory: String, loadingCategory: String});
const role = useAuiState(state => state.message.role);
const tickets = useAuiState(state => state.message.metadata.custom?.uniticket?.tickets || []);
const {gettext} = useI18n();
</script>

<template>
<MessagePrimitiveRoot class="assistant-row">
    <div class="assistant-msg" :class="role === 'assistant' ? 'assistant-msg--assistant' : 'assistant-msg--user'"
         :data-testid="role === 'assistant' ? 'assistant-assistant-message' : 'assistant-user-message'">
        <span class="assistant-author">{{ role === 'assistant' ? gettext('Assistente') : gettext('Tu') }}</span>
        <MessagePrimitiveParts />
        <TicketResults v-if="role === 'assistant' && tickets.length" :tickets="tickets"
            :selected-category="selectedCategory" :loading-category="loadingCategory" />
    </div>
</MessagePrimitiveRoot>
</template>

<style>
.assistant-row { display: flex; flex-direction: column; flex-shrink: 0; }
</style>
