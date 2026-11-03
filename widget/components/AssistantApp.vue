<script setup>
import {AuiProvider} from '@assistant-ui/vue';
import {useTicketInteractions} from '../composables/useTicketInteractions.js';
import AssistantWidget from './AssistantWidget.vue';

const props = defineProps({root: {type: Object, required: true}, csrfToken: {type: String, required: true}});
const interactions = useTicketInteractions(props.root, props.csrfToken);
</script>

<template>
    <AuiProvider :config="interactions.config">
        <AssistantWidget :interactions="interactions" :root="root" />
    </AuiProvider>
</template>
