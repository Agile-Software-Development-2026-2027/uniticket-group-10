import {defineConfig} from 'vite';
import {fileURLToPath} from 'node:url';

export default defineConfig({
    // I template Vue restano nell’HTML Django: è necessaria la build con compilatore.
    resolve: {alias: {vue: 'vue/dist/vue.esm-bundler.js'}},
    define: {
        'process.env.NODE_ENV': JSON.stringify('production'),
        __VUE_OPTIONS_API__: true,
        __VUE_PROD_DEVTOOLS__: false,
        __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: false
    },
    build: {
        // Cartella generata e ignorata da Git; Docker la copia fuori dal mount dei sorgenti.
        outDir: fileURLToPath(new URL('./frontend-dist', import.meta.url)),
        emptyOutDir: true,
        lib: {
            entry: fileURLToPath(new URL('./extensions/assistant/static/assistant-entry.js', import.meta.url)),
            name: 'UniTicketAssistant',
            formats: ['iife'],
            fileName: () => 'assistant.js',
            cssFileName: 'assistant'
        }
    }
});
