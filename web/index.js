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
const ALL_RATINGS = ["g", "s", "q", "e"];

const PANEL_CSS = `
.dbb-panel{width:100%;min-width:0;background:#1d1d22;border:1px solid #3a3a42;border-radius:8px;
  padding:8px;font:12px/1.5 "Segoe UI","Microsoft YaHei",sans-serif;color:#d8d8de;display:flex;flex-direction:column;gap:6px;height:100%;box-sizing:border-box}
.dbb-panel input[type=text],.dbb-panel select{background:#141419;border:1px solid #3a3a42;color:#d8d8de;
  border-radius:5px;padding:3px 7px;outline:none;font:inherit;min-width:0}
.dbb-panel input:disabled,.dbb-panel select:disabled{opacity:.45;cursor:not-allowed}
.dbb-panel button,.dbb-lightbox button{background:#33333c;border:1px solid #3a3a42;color:#d8d8de;
  border-radius:5px;padding:3px 10px;cursor:pointer;font:inherit}
.dbb-panel button:hover:not(:disabled),.dbb-lightbox button:hover{background:#3e3e49}
.dbb-panel button.primary{background:#4f8cff;border-color:#4f8cff;color:#fff;font-weight:600}
.dbb-panel button:disabled,.dbb-lightbox button:disabled{opacity:.45;cursor:not-allowed}
.dbb-chip{background:transparent;border:1px solid #3a3a42;border-radius:10px;padding:1px 8px;font-size:11px;cursor:pointer;opacity:.45}
.dbb-chip.on{opacity:1;border-color:currentColor}
.dbb-searchwrap{position:relative;flex:1;min-width:0}
.dbb-searchwrap input{width:100%;box-sizing:border-box}
.dbb-ac{position:absolute;top:100%;left:0;right:0;background:#141419;border:1px solid #3a3a42;border-radius:5px;z-index:50;max-height:160px;overflow-y:auto;display:none}
.dbb-ac div{padding:3px 8px;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.dbb-ac div:hover{background:#33333c}
.dbb-lb-tags{display:flex;flex-wrap:wrap;gap:4px;max-width:92vw;justify-content:center}
.dbb-lb-tags span{background:#33333c;border:1px solid #3a3a42;border-radius:10px;padding:1px 8px;font-size:11px;cursor:pointer;color:#d8d8de}
.dbb-lb-tags span:hover{background:#3e3e49}
.dbb-row{display:flex;gap:6px;align-items:center}
.dbb-mode{display:flex;gap:2px;background:#141419;border:1px solid #3a3a42;border-radius:5px;padding:2px}
.dbb-mode button{border:none;background:none;padding:2px 9px;border-radius:4px}
.dbb-mode button.on{background:#4f8cff;color:#fff}
.dbb-status{color:#8a8a94;font-size:11px;background:#141419;border-radius:5px;padding:3px 8px;display:flex;gap:14px}
.dbb-status b{color:#d8d8de}
.dbb-status .err{color:#ff5f56}
.dbb-grid{flex:1;overflow:auto;display:grid;grid-template-columns:repeat(auto-fill,140px);grid-auto-rows:140px;gap:6px;min-height:120px;align-content:start}
.dbb-grid .thumb{position:relative;border-radius:5px;overflow:hidden;cursor:pointer;border:2px solid transparent;background:#141419}
.dbb-grid .thumb img{width:100%;height:100%;display:block;object-fit:cover}
.dbb-grid .thumb.sel{border-color:#4f8cff;box-shadow:0 0 0 2px rgba(79,140,255,.35)}
.dbb-grid .thumb .badge{position:absolute;top:3px;left:3px;font-size:9px;border-radius:3px;padding:0 4px;color:#fff}
.dbb-empty{color:#8a8a94;text-align:center;padding:34px 10px;grid-column:1/-1}
.dbb-empty .big{font-size:26px;margin-bottom:6px}
.dbb-footer{min-height:34px;border:1px dashed #3a3a42;border-radius:5px;padding:4px 8px;font-size:11px;color:#8a8a94;display:flex;gap:6px;align-items:center}
.dbb-footer b{color:#d8d8de}
.dbb-lightbox{position:fixed;inset:0;background:rgba(10,10,14,.82);z-index:9999;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px}
.dbb-lightbox .dbb-lb-bar{display:flex;gap:8px}
.dbb-lightbox img{max-width:92vw;max-height:84vh;border-radius:6px;box-shadow:0 6px 40px rgba(0,0,0,.6)}
.dbb-lightbox .dbb-lb-msg{color:#ff5f56;font-size:13px;text-align:center;max-width:80vw}
`;

function injectCss() {
  if (document.getElementById("dbb-css")) return;
  const style = document.createElement("style");
  style.id = "dbb-css";
  style.textContent = PANEL_CSS;
  document.head.appendChild(style);
}

async function apiSearch(stateJson, conditions, proxy) {
  const resp = await fetch(`${API_BASE}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ state_json: stateJson, conditions, proxy }),
  });
  return resp.json();
}

async function apiPage(stateJson, page, proxy) {
  const resp = await fetch(`${API_BASE}/page`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ state_json: stateJson, page, proxy }),
  });
  return resp.json();
}

async function apiAction(stateJson, action, mode, proxy, postId, index) {
  const resp = await fetch(`${API_BASE}/action`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ state_json: stateJson, action, mode, post_id: postId, index, proxy }),
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
    this.proxyWidget = node.widgets?.find((w) => w.name === "proxy");
    this._initialized = false;
    injectCss();
    this.buildDom();
    // widget 值在 onConfigure(工作流恢复)后才就绪;新节点无 configure 触发,setTimeout 兜底
    setTimeout(() => this.init(), 0);
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
        <div class="dbb-searchwrap">
          <input type="text" id="dbb-search" placeholder="标签搜索(逗号分隔)…">
          <div class="dbb-ac" id="dbb-ac"></div>
        </div>
        <input type="text" id="dbb-exclude" placeholder="排除标签(逗号分隔)…" style="width:110px" title="含任一排除标签的帖子不出现">
        <button class="primary" id="dbb-search-btn">搜索</button>
      </div>
      <div class="dbb-row">
        <div class="dbb-mode">
          <button id="dbb-mode-manual" class="on">普通</button>
          <button id="dbb-mode-auto">自动</button>
          <button id="dbb-mode-list">列表</button>
        </div>
        <button disabled title="后续版本">▶ 自动</button>
        <button id="dbb-reset-cursor" disabled>⟲ 重置游标</button>
        <button id="dbb-list-clear" title="清空输出列表">清空列表</button>
        <input type="text" id="dbb-outfilter" disabled style="flex:1" title="T4 开放" placeholder="输出过滤标签(后续版本)">
      </div>
      <div class="dbb-row">
        <span style="color:#8a8a94;font-size:11px">评级</span>
        ${ALL_RATINGS.map((r) => `<button class="dbb-chip on" data-r="${r}" style="color:${RATING_COLOR[r]}">${RATING_LABEL[r]}</button>`).join("")}
        <select id="dbb-sort" style="margin-left:auto">
          <option value="new">最新</option>
          <option value="score">评分</option>
          <option value="random">随机</option>
        </select>
        <span style="color:#8a8a94;font-size:11px">每页</span>
        <select id="dbb-perpage">
          <option value="20">20</option>
          <option value="40" selected>40</option>
          <option value="60">60</option>
        </select>
      </div>
      <div class="dbb-status"><span id="dbb-status-text">普通 · 游标 — · 已选 — · 列表 0 · 失败 0</span><span id="dbb-err" class="err" style="margin-left:auto"></span></div>
      <div class="dbb-row">
        <button id="dbb-prev" disabled>‹ 上一页</button>
        <input type="text" id="dbb-page" value="1" style="width:44px;text-align:center" title="当前页,回车跳转">
        <button id="dbb-jump">跳转</button>
        <button id="dbb-next" disabled>下一页 ›</button>
      </div>
      <div class="dbb-grid" id="dbb-grid"></div>
      <div class="dbb-footer" id="dbb-footer">
        <span id="dbb-footer-text" style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">未选中 — 点击缩略图选中;执行队列输出所选帖子</span>
        <input type="text" id="dbb-list-pos" value="1" style="width:34px;text-align:center" title="插入位置(1 起)">
        <button id="dbb-list-insert" title="把选中帖插入列表指定位置">插入</button>
        <button id="dbb-list-toggle">加入列表</button>
      </div>
    `;
    el.querySelector("#dbb-search-btn").onclick = () => this.doSearch();
    this.page = 1;
    this.hasNext = false;
    this.pageInput = el.querySelector("#dbb-page");
    this.prevBtn = el.querySelector("#dbb-prev");
    this.nextBtn = el.querySelector("#dbb-next");
    this.prevBtn.onclick = () => this.gotoPage(this.page - 1);
    this.nextBtn.onclick = () => this.gotoPage(this.page + 1);
    el.querySelector("#dbb-jump").onclick = () => this.jumpToPage();
    this.pageInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") this.jumpToPage();
    });
    this.modeManualBtn = el.querySelector("#dbb-mode-manual");
    this.modeAutoBtn = el.querySelector("#dbb-mode-auto");
    this.modeListBtn = el.querySelector("#dbb-mode-list");
    this.resetBtn = el.querySelector("#dbb-reset-cursor");
    this.listToggleBtn = el.querySelector("#dbb-list-toggle");
    this.listInsertBtn = el.querySelector("#dbb-list-insert");
    this.listClearBtn = el.querySelector("#dbb-list-clear");
    this.modeManualBtn.onclick = () => this.setMode("manual");
    this.modeAutoBtn.onclick = () => this.setMode("auto");
    this.modeListBtn.onclick = () => this.setMode("list");
    this.resetBtn.onclick = () => this.modeAction("reset_cursor");
    this.listToggleBtn.onclick = () => this.toggleListForSelection();
    this.listInsertBtn.onclick = () => {
      const state = parseWidget(this.widget?.value);
      const sel = state?.selection;
      if (sel == null) return this.setError("先选中一张帖子再插入");
      if ((state?.outlist || []).includes(sel)) return this.setError("该帖已在列表中");
      const pos = Number(el.querySelector("#dbb-list-pos").value.trim());
      this.listAction("insert_to_list", sel, Number.isInteger(pos) && pos >= 1 ? pos - 1 : 0);
    };
    this.listClearBtn.onclick = () => this.listAction("clear_list");
    el.querySelectorAll(".dbb-chip").forEach((c) => {
      c.onclick = () => {
        // 至少保留一个评级:全关 = 不过滤,语义不清
        if (c.classList.contains("on") && el.querySelectorAll(".dbb-chip.on").length === 1) return;
        c.classList.toggle("on");
      };
    });
    this.initAutocomplete(el);
    this.grid = el.querySelector("#dbb-grid");
    this.footer = el.querySelector("#dbb-footer");
    this.statusText = el.querySelector("#dbb-status-text");
    this.errEl = el.querySelector("#dbb-err");
    this.node.addDOMWidget("browser_panel", "div", el, { serialize: false });
  }

  init() {
    if (this._initialized) return;  // onConfigure 与 setTimeout 可能都触发,只初始化一次
    this._initialized = true;
    // 重开工作流:会话在 widget 里,控件还原筛选条件并重拉当前页(ADR-0002)
    const state = parseWidget(this.widget?.value);
    if (state?.conditions) {
      this.syncControls(state.conditions);
      if (state.page && state.page > 1) this.gotoPage(state.page);
      else this.doSearch();
    } else {
      this.renderEmpty("未浏览 — 点击「搜索」加载 danbooru 最新帖子");
    }
  }

  initAutocomplete(el) {
    const input = el.querySelector("#dbb-search");
    const box = el.querySelector("#dbb-ac");
    let timer = null;
    let seq = 0;  // 丢弃过期响应:慢请求返回时输入框已输入新内容
    const hide = () => { box.style.display = "none"; };
    input.addEventListener("input", () => {
      clearTimeout(timer);
      const q = input.value.trim();
      if (!q) return hide();
      const mySeq = ++seq;
      timer = setTimeout(async () => {
        try {
          const resp = await fetch(`${API_BASE}/tags?q=${encodeURIComponent(q)}`);
          const data = await resp.json();
          if (mySeq !== seq) return;
          if (data.error || !data.tags?.length) return hide();
          box.innerHTML = "";
          data.tags.slice(0, 8).forEach((t) => {
            const div = document.createElement("div");
            div.textContent = t;
            div.onmousedown = () => {
              // 补全语义:替换正在输入的最后一段,而不是追加
              const words = input.value.trim().split(/[,\s]+/).filter(Boolean);
              if (words.length) words[words.length - 1] = t;
              else words.push(t);
              input.value = words.join(" ");
              hide();
            };
            box.appendChild(div);
          });
          box.style.display = "block";
        } catch {
          if (mySeq === seq) hide();
        }
      }, 200);
    });
    input.addEventListener("blur", () => setTimeout(hide, 150));
  }

  addTagToSearch(tag) {
    const input = this.el.querySelector("#dbb-search");
    const cur = input.value.trim();
    input.value = cur ? `${cur}, ${tag}` : tag;
  }

  readConditions() {
    const tags = this.el.querySelector("#dbb-search").value.trim().split(/[,\s]+/).filter(Boolean);
    const excludeTags = this.el.querySelector("#dbb-exclude").value.trim().split(/[,\s]+/).filter(Boolean);
    const ratings = [...this.el.querySelectorAll(".dbb-chip.on")].map((c) => c.dataset.r);
    return {
      site: this.el.querySelector("#dbb-site").value,
      tags,
      exclude_tags: excludeTags,
      ratings,
      sort: this.el.querySelector("#dbb-sort").value,
      per_page: +this.el.querySelector("#dbb-perpage").value,
    };
  }

  syncControls(c) {
    this.el.querySelector("#dbb-search").value = (c.tags || []).join(", ");
    this.el.querySelector("#dbb-exclude").value = (c.exclude_tags || []).join(", ");
    this.el.querySelectorAll(".dbb-chip").forEach((chip) => {
      chip.classList.toggle("on", (c.ratings || ALL_RATINGS).includes(chip.dataset.r));
    });
    this.el.querySelector("#dbb-sort").value = c.sort || "new";
    this.el.querySelector("#dbb-perpage").value = String(c.per_page || 40);
  }

  async doSearch() {
    this.setError("");
    try {
      const conditions = this.readConditions();
      const res = await apiSearch(this.widget?.value || "", conditions, this.proxyWidget?.value || "");
      if (res.error) {
        this.setError(res.error);
        return;
      }
      this.applyResult(res);
    } catch (e) {
      this.setError(`搜索失败: ${e.message || e}`);
    }
  }

  async gotoPage(n) {
    this.setError("");
    try {
      const res = await apiPage(this.widget?.value || "", n, this.proxyWidget?.value || "");
      if (res.error) {
        this.setError(res.error);
        return;
      }
      this.applyResult(res);
    } catch (e) {
      this.setError(`翻页失败: ${e.message || e}`);
    }
  }

  jumpToPage() {
    const n = Number(this.pageInput.value.trim());
    if (!Number.isInteger(n) || n < 1) return this.setError("页码必须是 ≥1 的整数");
    if (n === this.page) return;
    this.gotoPage(n);
  }

  setMode(mode) {
    this.modeAction("set_mode", mode);
  }

  async modeAction(action, mode) {
    this.setError("");
    try {
      const res = await apiAction(this.widget?.value || "", action, mode, this.proxyWidget?.value || "");
      if (res.error) {
        this.setError(res.error);
        return;
      }
      this.applyStateOnly(res.state_json);
    } catch (e) {
      this.setError(`模式操作失败: ${e.message || e}`);
    }
  }

  async listAction(action, postId, index) {
    this.setError("");
    try {
      const res = await apiAction(
        this.widget?.value || "", action, undefined, this.proxyWidget?.value || "", postId, index,
      );
      if (res.error) {
        this.setError(res.error);
        return;
      }
      this.applyStateOnly(res.state_json);
    } catch (e) {
      this.setError(`列表操作失败: ${e.message || e}`);
    }
  }

  toggleListForSelection() {
    const state = parseWidget(this.widget?.value);
    const sel = state?.selection;
    if (sel == null) return this.setError("先选中一张帖子再操作列表");
    const inList = (state?.outlist || []).includes(sel);
    this.listAction(inList ? "remove_from_list" : "add_to_list", sel);
  }

  applyStateOnly(stateJson) {
    this.widget.value = stateJson;
    const state = parseWidget(stateJson);
    this.updateMode(state?.mode);
    this.updateStatus(state);
    this.updateListToggle(state?.selection ?? null);
  }

  updateMode(mode) {
    const m = mode || "manual";
    this.modeManualBtn.classList.toggle("on", m === "manual");
    this.modeAutoBtn.classList.toggle("on", m === "auto");
    this.modeListBtn.classList.toggle("on", m === "list");
    this.resetBtn.disabled = m !== "auto";
  }

  applyResult(res) {
    this.widget.value = res.state_json;
    this.page = res.page;
    this.hasNext = !!res.has_next;
    this.pageInput.value = res.page;
    this.updateNavButtons();
    this.renderGrid(res.posts);
    const state = parseWidget(res.state_json);
    this.updateMode(state?.mode);
    this.updateStatus(state);
    this.renderFooter(state?.selection ?? null);
    // 后端保留的选中项要重新画上蓝色描边(ADR-0002)
    const sel = state?.selection;
    if (sel != null) {
      this.grid.querySelectorAll(".thumb").forEach((t) => {
        t.classList.toggle("sel", +t.dataset.id === sel);
      });
    }
  }

  updateNavButtons() {
    this.prevBtn.disabled = !this.page || this.page <= 1;
    this.nextBtn.disabled = !this.hasNext;
  }

  renderGrid(posts) {
    if (!posts?.length) {
      this.renderEmpty("没有符合条件的帖子");
      return;
    }
    this.grid.innerHTML = posts
      .map(
        (p, i) => `
      <div class="thumb" data-id="${p.id}" title="#${p.id} · ${RATING_LABEL[p.rating] || p.rating} · ★${p.score}">
        <span class="badge" style="background:${RATING_COLOR[p.rating] || "#666"}">${p.id}</span>
        <img src="${API_BASE}/image?url=${encodeURIComponent(p.preview_url)}" alt="#${p.id}" loading="${i < 12 ? "eager" : "lazy"}" referrerpolicy="no-referrer" onerror="this.style.visibility='hidden'">
      </div>`
      )
      .join("");
    this.grid.querySelectorAll(".thumb").forEach((t) => {
      t.onclick = () => this.selectPost(+t.dataset.id);
      // 双击:两次单击的 toggle 互相抵消,选中状态不变,可安全共存
      t.ondblclick = () => this.showLightbox(+t.dataset.id);
    });
  }

  findPost(state, id) {
    return (state.pages || []).flatMap((pg) => pg.posts).find((p) => p.id === id) || null;
  }

  showLightbox(id) {
    const state = parseWidget(this.widget?.value);
    if (!state) return;
    const post = this.findPost(state, id);
    if (!post) return;
    const raw = post.raw || {};
    const sample = raw.large_file_url || raw.preview_file_url || post.file_url;
    const original = raw.file_url || post.file_url;
    const hasOriginal = original && original !== sample;
    const overlay = document.createElement("div");
    overlay.className = "dbb-lightbox";
    overlay.innerHTML = `
      <div class="dbb-lb-bar">
        <button class="dbb-lb-toggle">原图</button>
        <button class="dbb-lb-close">关闭</button>
      </div>
      <div class="dbb-lb-msg"></div>
      <img alt="大图预览">
      <div class="dbb-lb-tags"></div>
    `;
    const img = overlay.querySelector("img");
    const msg = overlay.querySelector(".dbb-lb-msg");
    const toggle = overlay.querySelector(".dbb-lb-toggle");
    // 点击 tag 直接加入搜索框(最多展示 40 个,避免超长标签列表)
    overlay.querySelector(".dbb-lb-tags").append(
      ...post.tags.slice(0, 40).map((t) => {
        const chip = document.createElement("span");
        chip.textContent = t;
        chip.title = `点击加入搜索框:${t}`;
        chip.onclick = () => this.addTagToSearch(t);
        return chip;
      }),
    );
    let showingOriginal = false;
    const onKey = (e) => {
      if (e.key === "Escape") close();
    };
    const close = () => {
      overlay.remove();
      document.removeEventListener("keydown", onKey);
    };
    const fail = (text) => {
      img.style.display = "none";
      msg.style.display = "block";
      msg.textContent = text;
    };
    const load = (url, label) => {
      if (!url) return fail("没有可显示的图片");
      msg.style.display = "none";
      img.style.display = "block";
      img.src = `${API_BASE}/image?url=${encodeURIComponent(url)}`;
      toggle.textContent = label;
    };
    img.onerror = () => fail("图片加载失败(可能已删除或网络异常)");
    toggle.onclick = () => {
      showingOriginal = !showingOriginal;
      load(showingOriginal ? original : sample, showingOriginal ? "缩略图" : "原图");
    };
    overlay.querySelector(".dbb-lb-close").onclick = close;
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) close();
    });
    document.addEventListener("keydown", onKey);
    document.body.appendChild(overlay);
    if (post.animated && ["webm", "swf"].includes(raw.file_ext)) {
      toggle.disabled = true;
      fail("动画帖(webm/swf),暂不支持大图预览");
      return;
    }
    if (!hasOriginal) toggle.disabled = true;  // 原图不可用时切换是 no-op
    load(sample, "原图");
  }

  renderEmpty(msg) {
    this.grid.innerHTML = `<div class="dbb-empty"><div class="big">🔍</div>${msg}</div>`;
  }

  selectPost(id) {
    const state = parseWidget(this.widget?.value);
    if (!state || !state.pages) return;
    state.selection = state.selection === id ? null : id;
    if (state.selection != null && state.mode !== "list") {
      // 与后端 select() 语义一致:游标同步到选中帖(自动模式从这继续);列表模式游标是列表位置
      const idx = (state.pages || []).flatMap((pg) => pg.posts).findIndex((p) => p.id === id);
      if (idx >= 0) state.cursor = idx;
    }
    this.widget.value = JSON.stringify(state);
    this.grid.querySelectorAll(".thumb").forEach((t) => {
      t.classList.toggle("sel", +t.dataset.id === state.selection);
    });
    this.updateStatus(state);
    this.renderFooter(state.selection);
  }

  renderFooter(selId) {
    const text = this.el.querySelector("#dbb-footer-text");
    const state = parseWidget(this.widget?.value);
    if (!state || selId == null) {
      text.textContent = "未选中 — 点击缩略图选中;执行队列输出所选帖子";
      this.updateListToggle(null);
      return;
    }
    const post = this.findPost(state, selId);
    text.innerHTML = post
      ? `已选 <b>#${post.id}</b> · 提示词:${post.tags.join(", ")}`
      : `已选 <b>#${selId}</b>`;
    this.updateListToggle(selId);
  }

  updateListToggle(selId) {
    const state = parseWidget(this.widget?.value);
    const inList = selId != null && (state?.outlist || []).includes(selId);
    this.listToggleBtn.textContent = inList ? "从列表移除" : "加入列表";
  }

  updateStatus(state) {
    const modeLabel = { manual: "普通", auto: "自动", list: "列表" }[state?.mode] || "普通";
    const sel = state?.selection != null ? `#${state.selection}` : "—";
    // 手动:游标是当前页内的位置;自动:游标跨全部已加载;列表:游标对列表长度
    const curPage = (state?.pages || []).find((pg) => pg.number === (state?.page || 1));
    const total = (state?.pages || []).reduce((n, pg) => n + pg.posts.length, 0);
    const nPosts = state?.mode === "auto" ? total : (curPage ? curPage.posts.length : 0);
    const cur = state?.cursor != null
      ? (state?.mode === "list" ? `${state.cursor}/${state.outlist.length}` : `${state.cursor}/${nPosts}`)
      : "—";
    const nList = state?.outlist?.length || 0;
    this.statusText.innerHTML = `${modeLabel} · 游标 <b>${cur}</b> · 已选 <b>${sel}</b> · 列表 <b>${nList}</b> · 失败 <b>0</b>`;
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
    // 工作流恢复:configure 在 onNodeCreated 之后才把 widget 值填上,
    // 面板初始化必须延到这里才能读到会话(ADR-0002 恢复)
    const onConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
      onConfigure?.apply(this, arguments);
      this._browserPanel?.init();
    };
    // 执行后把推进后的会话写回 widget(自动模式游标前进;ADR-0002 真相在 widget)
    const onExecuted = nodeType.prototype.onExecuted;
    nodeType.prototype.onExecuted = function (outputs) {
      onExecuted?.apply(this, arguments);
      // ui 字典的值是数组([value]),兼容非数组
      const s = Array.isArray(outputs?.SESSION) ? outputs.SESSION[0] : outputs?.SESSION;
      if (s != null && this._browserPanel) {
        this._browserPanel.applyStateOnly(String(s));
      }
    };
  },
});
