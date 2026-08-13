import { app } from "../../scripts/app.js";

/**
 * Danbooru Browser 浏览面板(T1:danbooru + 手动输出)。
 *
 * 布局采用原型变体 A(经典工具栏)。会话(搜索条件/已加载页/选中项)存于
 * "session" widget 值,随工作流 JSON 序列化(ADR-0002);面板展示走
 * /danbooru_browser/search 路由(ADR-0001)。
 */

const API_BASE = "/danbooru_browser";
const RATING_LABEL = { g: "普通", s: "敏感", q: "可疑", e: "R18" };
const RATING_COLOR = { g: "#4f8cff", s: "#ffb454", q: "#ff9d45", e: "#ff7ab6" };
const DEFAULT_CONDITIONS = {
  site: "danbooru",
  tags: [],
  exclude_tags: [],
  ratings: ["g", "s", "q", "e"],
  sort: "new",
  per_page: 40,
};

const PANEL_CSS = `
.dbb-panel{width:440px;background:#1d1d22;border:1px solid #3a3a42;border-radius:8px;
  padding:8px;font:12px/1.5 "Segoe UI","Microsoft YaHei",sans-serif;color:#d8d8de;display:flex;flex-direction:column;gap:6px;height:100%;box-sizing:border-box}
.dbb-panel input[type=text],.dbb-panel select{background:#141419;border:1px solid #3a3a42;color:#d8d8de;
  border-radius:5px;padding:3px 7px;outline:none;font:inherit;min-width:0}
.dbb-panel input:disabled,.dbb-panel select:disabled{opacity:.45;cursor:not-allowed}
.dbb-panel button{background:#33333c;border:1px solid #3a3a42;color:#d8d8de;border-radius:5px;
  padding:3px 10px;cursor:pointer;font:inherit}
.dbb-panel button:hover:not(:disabled){background:#3e3e49}
.dbb-panel button.primary{background:#4f8cff;border-color:#4f8cff;color:#fff;font-weight:600}
.dbb-panel button:disabled{opacity:.45;cursor:not-allowed}
.dbb-row{display:flex;gap:6px;align-items:center}
.dbb-mode{display:flex;gap:2px;background:#141419;border:1px solid #3a3a42;border-radius:5px;padding:2px}
.dbb-mode button{border:none;background:none;padding:2px 9px;border-radius:4px}
.dbb-mode button.on{background:#4f8cff;color:#fff}
.dbb-status{color:#8a8a94;font-size:11px;background:#141419;border-radius:5px;padding:3px 8px;display:flex;gap:14px}
.dbb-status b{color:#d8d8de}
.dbb-status .err{color:#ff5f56}
.dbb-grid{flex:1;overflow-y:auto;display:grid;grid-template-columns:repeat(3,1fr);gap:6px;min-height:120px;align-content:start}
.dbb-grid .thumb{position:relative;border-radius:5px;overflow:hidden;cursor:pointer;border:2px solid transparent;background:#141419}
.dbb-grid .thumb img{width:100%;display:block;aspect-ratio:1;object-fit:cover}
.dbb-grid .thumb.sel{border-color:#4f8cff;box-shadow:0 0 0 2px rgba(79,140,255,.35)}
.dbb-grid .thumb .badge{position:absolute;top:3px;left:3px;font-size:9px;border-radius:3px;padding:0 4px;color:#fff}
.dbb-empty{color:#8a8a94;text-align:center;padding:34px 10px;grid-column:1/-1}
.dbb-empty .big{font-size:26px;margin-bottom:6px}
.dbb-footer{min-height:34px;border:1px dashed #3a3a42;border-radius:5px;padding:5px 8px;font-size:11px;color:#8a8a94;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dbb-footer b{color:#d8d8de}
`;

function injectCss() {
  if (document.getElementById("dbb-css")) return;
  const style = document.createElement("style");
  style.id = "dbb-css";
  style.textContent = PANEL_CSS;
  document.head.appendChild(style);
}

async function apiSearch(stateJson, conditions) {
  const resp = await fetch(`${API_BASE}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ state_json: stateJson, conditions }),
  });
  return resp.json();
}

function parseWidget(json) {
  if (!json) return null;
  try {
    const state = JSON.parse(json);
    return state && typeof state === "object" ? state : null;
  } catch {
    return null;
  }
}

class BrowserPanel {
  constructor(node) {
    this.node = node;
    this.widget = node.widgets?.find((w) => w.name === "session");
    injectCss();
    this.buildDom();
    this.init();
  }

  buildDom() {
    const el = (this.el = document.createElement("div"));
    el.className = "dbb-panel";
    el.innerHTML = `
      <div class="dbb-row">
        <select id="dbb-site" title="T1 仅 danbooru">
          <option value="danbooru" selected>danbooru</option>
          <option disabled>gelbooru (后续版本)</option>
          <option disabled>civitai (后续版本)</option>
        </select>
        <input type="text" id="dbb-search" disabled title="T2 开放" placeholder="标签搜索(T2)…" style="flex:1">
        <input type="text" id="dbb-exclude" disabled title="T2 开放" placeholder="排除标签(T2)…">
        <button class="primary" id="dbb-search-btn">搜索</button>
      </div>
      <div class="dbb-row">
        <div class="dbb-mode">
          <button class="on" disabled>普通</button>
          <button disabled title="后续版本">自动</button>
          <button disabled title="后续版本">列表</button>
        </div>
        <button disabled title="后续版本">▶ 自动</button>
        <button disabled title="后续版本">⟲ 重置游标</button>
        <input type="text" id="dbb-outfilter" disabled style="flex:1" title="T4 开放" placeholder="输出过滤标签(后续版本)">
      </div>
      <div class="dbb-row">
        <span style="color:#8a8a94;font-size:11px">评级</span>
        ${["g", "s", "q", "e"].map((r) => `<span class="dbb-chip" data-r="${r}" style="color:${RATING_COLOR[r]};border:1px solid ${RATING_COLOR[r]}33;border-radius:10px;padding:1px 8px;font-size:11px;opacity:.8">${RATING_LABEL[r]}</span>`).join("")}
        <select id="dbb-sort" disabled style="margin-left:auto"><option>最新</option><option disabled>评分 (后续版本)</option><option disabled>随机 (后续版本)</option></select>
        <span style="color:#8a8a94;font-size:11px">每页</span>
        <select id="dbb-perpage" disabled><option>40</option><option disabled>20 (后续版本)</option><option disabled>60 (后续版本)</option></select>
      </div>
      <div class="dbb-status"><span id="dbb-status-text">普通 · 游标 — · 已选 — · 列表 0 · 失败 0</span><span id="dbb-err" class="err" style="margin-left:auto"></span></div>
      <div class="dbb-grid" id="dbb-grid"></div>
      <div class="dbb-footer" id="dbb-footer">未选中 — 点击缩略图选中;执行队列输出所选帖子</div>
    `;
    el.querySelector("#dbb-search-btn").onclick = () => this.doSearch();
    this.grid = el.querySelector("#dbb-grid");
    this.footer = el.querySelector("#dbb-footer");
    this.statusText = el.querySelector("#dbb-status-text");
    this.errEl = el.querySelector("#dbb-err");
    this.node.addDOMWidget("browser_panel", "div", el, { serialize: false });
  }

  init() {
    // 重开工作流:会话在 widget 里,自动重拉第 1 页(ADR-0002)
    const state = parseWidget(this.widget?.value);
    if (state?.conditions) this.doSearch();
    else this.renderEmpty("未浏览 — 点击「搜索」加载 danbooru 最新帖子");
  }

  async doSearch() {
    this.setError("");
    try {
      const conditions = { ...DEFAULT_CONDITIONS, site: this.el.querySelector("#dbb-site").value };
      const res = await apiSearch(this.widget?.value || "", conditions);
      if (res.error) {
        this.setError(res.error);
        return;
      }
      this.widget.value = res.state_json;
      this.renderGrid(res.posts);
      const state = parseWidget(res.state_json);
      this.updateStatus(state);
      this.renderFooter(state?.selection ?? null);
      // 重开工作流:后端保留的选中项要重新画上蓝色描边(ADR-0002)
      const sel = state?.selection;
      if (sel != null) {
        this.grid.querySelectorAll(".thumb").forEach((t) => {
          t.classList.toggle("sel", +t.dataset.id === sel);
        });
      }
    } catch (e) {
      this.setError(`搜索失败: ${e.message || e}`);
    }
  }

  renderGrid(posts) {
    if (!posts?.length) {
      this.renderEmpty("没有符合条件的帖子");
      return;
    }
    this.grid.innerHTML = posts
      .map(
        (p) => `
      <div class="thumb" data-id="${p.id}" title="#${p.id} · ${RATING_LABEL[p.rating] || p.rating} · ★${p.score}">
        <span class="badge" style="background:${RATING_COLOR[p.rating] || "#666"}">${p.id}</span>
        <img src="${p.preview_url}" alt="#${p.id}" loading="lazy" referrerpolicy="no-referrer" onerror="this.style.visibility='hidden'">
      </div>`
      )
      .join("");
    this.grid.querySelectorAll(".thumb").forEach((t) => {
      t.onclick = () => this.selectPost(+t.dataset.id);
    });
  }

  renderEmpty(msg) {
    this.grid.innerHTML = `<div class="dbb-empty"><div class="big">🔍</div>${msg}</div>`;
  }

  selectPost(id) {
    const state = parseWidget(this.widget?.value);
    if (!state || !state.pages) return;
    state.selection = state.selection === id ? null : id;
    this.widget.value = JSON.stringify(state);
    this.grid.querySelectorAll(".thumb").forEach((t) => {
      t.classList.toggle("sel", +t.dataset.id === state.selection);
    });
    this.updateStatus(state);
    this.renderFooter(state.selection);
  }

  renderFooter(selId) {
    const state = parseWidget(this.widget?.value);
    if (!state || selId == null) {
      this.footer.textContent = "未选中 — 点击缩略图选中;执行队列输出所选帖子";
      return;
    }
    const post = (state.pages || []).flatMap((pg) => pg.posts).find((p) => p.id === selId);
    this.footer.innerHTML = post
      ? `已选 <b>#${post.id}</b> · 提示词:${post.tags.join(", ")}`
      : `已选 <b>#${selId}</b>`;
  }

  updateStatus(state) {
    const sel = state?.selection != null ? `#${state.selection}` : "—";
    const nPosts = (state?.pages || []).reduce((n, pg) => n + pg.posts.length, 0);
    const cur = state?.cursor != null ? `${state.cursor}/${nPosts}` : "—";
    const nList = state?.outlist?.length || 0;
    this.statusText.innerHTML = `普通 · 游标 <b>${cur}</b> · 已选 <b>${sel}</b> · 列表 <b>${nList}</b> · 失败 <b>0</b>`;
  }

  setError(msg) {
    this.errEl.textContent = msg || "";
  }
}

app.registerExtension({
  name: "DanbooruBrowser.Node",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== "DanbooruBrowserNode") return;
    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      onNodeCreated?.apply(this, arguments);
      this._browserPanel = new BrowserPanel(this);
    };
  },
});
