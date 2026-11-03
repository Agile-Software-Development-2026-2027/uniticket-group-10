<script>
import {useI18n} from '../../i18n/index.js';
import TicketCard from './TicketCard.vue';

export default {
    components: {TicketCard},
    setup: useI18n,
    props: {tickets: {type: Array, required: true}, selectedCategory: String, loadingCategory: String},
    data: () => ({visible: 3}),
    computed: {
        moreLabel() {
            const count = Math.min(3, this.tickets.length - this.visible);
            return this.gettext('Mostra un’altra richiesta', {count});
        },
    },
    methods: {
        async showMore() {
            const first = this.visible;
            this.visible += 3;
            await this.$nextTick();
            const links = this.$refs.results?.querySelectorAll('a');
            Array.from(links || []).slice(first).forEach(link => link.animate?.([{opacity: 0}, {opacity: 1}], {
                duration: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 80 : 180,
                easing: 'cubic-bezier(0.16, 1, 0.3, 1)',
            }));
            links?.[first]?.focus({preventScroll: true});
        },
    },
};
</script>

<template>
    <ul v-if="tickets.length" ref="results" class="assistant-results" :aria-label="gettext('Richieste suggerite')">
        <TicketCard v-for="ticket in tickets.slice(0, visible)" :key="ticket.category_id" :ticket="ticket"
                    :selected-category="selectedCategory" :loading-category="loadingCategory" />
    </ul>
    <button v-if="tickets.length > visible" class="assistant-more" type="button" @click="showMore">
        <span v-text="moreLabel"></span>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>
    </button>
</template>
