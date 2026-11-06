import {build} from 'esbuild';
import * as vue from 'vue';
import {parse, compileScript, compileTemplate, compileStyle} from 'vue/compiler-sfc';
import {createHash} from 'node:crypto';
import {copyFileSync, existsSync, readFileSync, writeFileSync} from 'node:fs';
import {dirname, join, relative, resolve} from 'node:path';

const outputDir = '../uniticket/extensions/assistant/static/chat/vendor';

const result = await build({
    entryPoints: ['main.js'], bundle: true, format: 'iife', platform: 'browser', target: 'es2022',
    outfile: join(outputDir, 'assistant-ui.js'), minify: true, legalComments: 'external',
    metafile: true,
    define: {'process.env.NODE_ENV': '"production"'},
    alias: {
        react: '@assistant-ui/tap/standalone-shim',
        'react/compiler-runtime': '@assistant-ui/tap/standalone-shim/compiler-runtime',
    },
    plugins: [{name: 'vue-components', setup(builder) {
        const styles = new Map();
        builder.onLoad({filter: /\.vue$/, namespace: 'file'}, ({path}) => {
            const {descriptor, errors} = parse(readFileSync(path, 'utf8'), {filename: path});
            if (errors.length) throw errors[0];
            const id = 'data-v-' + createHash('sha256').update(relative(process.cwd(), path)).digest('hex').slice(0, 8);
            const scoped = descriptor.styles.some(style => style.scoped);
            const script = compileScript(descriptor, {id, genDefaultAs: '__component'});
            const template = compileTemplate({source: descriptor.template.content, filename: path, id, scoped,
                compilerOptions: {bindingMetadata: script.bindings}});
            if (template.errors.length) throw template.errors[0];
            let contents = script.content + '\n' + template.code.replace('export function render', 'function render');
            contents += '\n__component.render = render;\nexport default __component;';
            if (scoped) contents += `\n__component.__scopeId = ${JSON.stringify(id)};`;
            if (descriptor.styles.length) {
                styles.set(path, descriptor.styles.map(style => {
                    const compiled = compileStyle({source: style.content, filename: path, id, scoped: style.scoped});
                    if (compiled.errors.length) throw compiled.errors[0];
                    return compiled.code;
                }).join('\n'));
                contents += `\nimport ${JSON.stringify(path + '?vue-style')};`;
            }
            return {contents, resolveDir: dirname(path)};
        });
        builder.onResolve({filter: /\?vue-style$/}, ({path}) => ({path: path.replace(/\?vue-style$/, ''), namespace: 'vue-style'}));
        builder.onLoad({filter: /.*/, namespace: 'vue-style'}, ({path}) => ({contents: styles.get(path), loader: 'css'}));
    }}, {name: 'existing-vue-runtime', setup(builder) {
        builder.onResolve({filter: /^vue$/}, () => ({path: 'vue', namespace: 'existing-vue'}));
        builder.onLoad({filter: /.*/, namespace: 'existing-vue'}, () => ({
            contents: `export const {${Object.keys(vue).filter(name => name !== 'default' && /^[\w$]+$/.test(name)).join(',')}} = window.Vue;`,
        }));
    }}],
});

// Distribute the licenses of the packages actually included in the browser bundle.
const packages = new Map();
for (const input of Object.keys(result.metafile.inputs).filter(input => input.startsWith('node_modules/'))) {
    let directory = dirname(resolve(input));
    while (directory.includes('node_modules')) {
        const manifest = join(directory, 'package.json');
        if (existsSync(manifest)) {
            const pkg = JSON.parse(readFileSync(manifest, 'utf8'));
            if (pkg.name && pkg.version) {
                const license = ['LICENSE', 'LICENSE.md', 'LICENSE.txt', 'license', 'license.md'].find(name => existsSync(join(directory, name)));
                packages.set(`${pkg.name}@${pkg.version}`, `${pkg.name}@${pkg.version} (${pkg.license || 'see package'})\n` +
                    (license ? readFileSync(join(directory, license), 'utf8') : `Source: https://www.npmjs.com/package/${pkg.name}`));
                break;
            }
        }
        directory = dirname(directory);
    }
}
writeFileSync(join(outputDir, 'THIRD-PARTY-LICENSES.txt'),
    [...packages].sort(([a], [b]) => a.localeCompare(b)).map(([, text]) => text).join('\n\n').replace(/[ \t\r]+$/gm, '').trimEnd() + '\n');

copyFileSync('node_modules/htmx.org/dist/htmx.min.js', join(outputDir, 'htmx.js'));
copyFileSync('node_modules/htmx.org/LICENSE', join(outputDir, 'htmx.LICENSE.txt'));
