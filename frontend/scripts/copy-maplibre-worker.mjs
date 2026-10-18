// MapLibre 6 loads its web worker from a file next to its own bundle, which Next.js does not copy.
// Copy it into public/ so it is served at /maplibre-gl-worker.mjs (see setWorkerUrl in WeatherGlobe).
import { copyFileSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";

const require = createRequire(import.meta.url);
const dist = dirname(require.resolve("maplibre-gl/package.json")) + "/dist";
mkdirSync("public", { recursive: true });
copyFileSync(join(dist, "maplibre-gl-worker.mjs"), join("public", "maplibre-gl-worker.mjs"));
console.log("copied maplibre-gl-worker.mjs to public/");
