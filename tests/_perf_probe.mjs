import fs from "node:fs";
import vm from "node:vm";
import { performance } from "node:perf_hooks";

let source = fs.readFileSync(new URL("../web/index.js", import.meta.url), "utf8");
source = source.replace(/^import .*?;\r?\n/, "");
source = source.slice(0, source.indexOf("app.registerExtension({"));
source += "\nglobalThis.__BrowserPanel = BrowserPanel;\n";
vm.runInThisContext(source, { filename: "web/index.js" });

const makeState = (lastOutput) => ({
  conditions: { site: "danbooru", tags: ["1girl"], ratings: ["g", "s", "q", "e"], sort: "new", per_page: 60 },
  pages: Array.from({ length: 5 }, (_, page) => ({
    number: page + 1,
    posts: Array.from({ length: 60 }, (_, index) => {
      const id = page * 60 + index + 1;
      return {
        id, site: "danbooru", file_url: `https://example.com/${id}.jpg`,
        sample_url: `https://example.com/sample/${id}.jpg`, preview_url: `https://example.com/preview/${id}.jpg`,
        tags: Array.from({ length: 80 }, (__, tag) => `tag_${tag}_${"x".repeat(20)}`),
        rating: "g", score: id, author: "tester", animated: false,
        raw: { tag_string: "x".repeat(1000), metadata: "y".repeat(1000) },
      };
    }),
  })),
  cursor: 0, selection: null, outlist: [], page: 5, mode: "auto",
  out_filter: [], failed: [], last_output: lastOutput,
});

const states = [JSON.stringify(makeState(1)), JSON.stringify(makeState(2))];
const panel = Object.create(globalThis.__BrowserPanel.prototype);
panel.widget = { value: states[0] };
panel._stateJson = states[0];
panel._state = JSON.parse(states[0]);
panel.listView = false;
panel.el = { querySelector: () => ({ textContent: "" }) };
panel.grid = { querySelectorAll: () => [] };
panel.updateMode = () => {};
panel.updateStatus = () => {};
panel.updateListToggle = () => {};
panel.applyMarks = () => {};

const nativeParse = JSON.parse;
let parses = 0;
JSON.parse = (...args) => { parses += 1; return nativeParse(...args); };
const iterations = 40;
const start = performance.now();
for (let i = 0; i < iterations; i += 1) panel.applyStateOnly(states[(i + 1) % 2]);
const elapsed = performance.now() - start;
JSON.parse = nativeParse;

console.log(JSON.stringify({ iterations, parses, elapsed_ms: Math.round(elapsed), state_mb: +(states[0].length / 1024 / 1024).toFixed(2) }));
if (parses !== iterations) {
  console.error(`FAIL: each state update should parse once, observed ${parses / iterations} parses/update`);
  process.exitCode = 1;
}

let pageCalls = 0;
globalThis.Image = class { set src(value) { this._src = value; } };
globalThis.apiPage = async (stateJson, page) => {
  pageCalls += 1;
  return { state_json: stateJson, posts: [{ id: page, preview_url: "https://example.com/thumb.jpg" }], page, has_next: true };
};
const pagePanel = Object.create(globalThis.__BrowserPanel.prototype);
pagePanel.widget = { value: states[0] };
pagePanel.proxyWidget = { value: "" };
pagePanel._stateJson = states[0];
pagePanel._state = nativeParse(states[0]);
pagePanel.page = 1;
pagePanel.hasNext = true;
pagePanel.prefetched = new Map();
pagePanel.setError = () => {};
pagePanel.applyResult = () => {};
pagePanel.prefetchNextPage();
await pagePanel.prefetched.get(2).start();
await pagePanel.gotoPage(2);
console.log(JSON.stringify({ next_page_api_calls: pageCalls }));
if (pageCalls !== 1) {
  console.error(`FAIL: prefetched next-page data should be reused, observed ${pageCalls} API calls`);
  process.exitCode = 1;
}

pageCalls = 0;
let appliedState = null;
const stalePanel = Object.create(globalThis.__BrowserPanel.prototype);
stalePanel.widget = { value: states[0] };
stalePanel.proxyWidget = { value: "" };
stalePanel._stateJson = states[0];
stalePanel._state = nativeParse(states[0]);
stalePanel.page = 1;
stalePanel.hasNext = true;
stalePanel.prefetched = new Map();
stalePanel.setError = () => {};
stalePanel.applyResult = (res) => { appliedState = res.state_json; };
stalePanel.prefetchNextPage();
stalePanel.widget.value = states[1];  // 选择/模式等操作使预取基线过期
await stalePanel.gotoPage(2);
await new Promise((resolve) => setTimeout(resolve, 550));
console.log(JSON.stringify({ stale_prefetch_api_calls: pageCalls }));
if (pageCalls !== 1 || appliedState !== states[1]) {
  console.error("FAIL: stale prefetch should be cancelled and must not overwrite the newer session");
  process.exitCode = 1;
}
