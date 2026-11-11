import { build, context } from "esbuild";
import { copyFile, mkdir } from "node:fs/promises";

const watch = process.argv.includes("--watch");
const demo = !process.argv.includes("--widget") && (watch || process.argv.includes("--demo"));
const options = {
  entryPoints: [demo ? "demo/main.tsx" : "src/embed.tsx"],
  bundle: true,
  outdir: demo ? "dist-demo" : process.env.WIDGET_OUTPUT_DIR || "dist-widget",
  entryNames: demo ? "demo" : "assistant-ui",
  format: "iife",
  globalName: demo ? "UniTicketDemo" : "UniTicketAssistant",
  platform: "browser",
  target: "es2022",
  jsx: "automatic",
  minify: !watch,
  define: { "process.env.NODE_ENV": JSON.stringify(watch ? "development" : "production") },
  legalComments: "linked",
  loader: { ".woff2": "file" },
  assetNames: "fonts/[name]-[hash]",
};

if (demo) {
  await mkdir("dist-demo/fonts", { recursive: true });
  await copyFile("demo/fonts/OFL.txt", "dist-demo/fonts/OFL.txt");
}

if (watch) {
  const compiler = await context(options);
  await compiler.watch();
  if (demo) {
    const { port } = await compiler.serve({ servedir: ".", host: "127.0.0.1" });
    console.log(`Anteprima UI: http://127.0.0.1:${port}`);
  }
} else {
  await build(options);
}
