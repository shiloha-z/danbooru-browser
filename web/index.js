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
.dbb-grid .thumb.sel{border:3px solid #4f8cff;box-shadow:0 0 0 3px rgba(79,140,255,.45)}
.dbb-grid .thumb.current{border:3px solid #ff5f56;box-shadow:0 0 0 3px rgba(255,95,86,.45)}
.dbb-grid .thumb.failed img{opacity:.35}
.dbb-grid .thumb.placeholder{display:flex;align-items:center;justify-content:center;color:#8a8a94;font-size:12px;cursor:pointer}
.dbb-grid .thumb .badge{position:absolute;top:3px;left:3px;font-size:9px;border-radius:3px;padding:0 4px;color:#fff}
.dbb-grid .thumb .fail-badge{position:absolute;top:3px;right:3px;width:16px;height:16px;border-radius:50%;background:#ff5f56;color:#fff;font-size:11px;line-height:16px;text-align:center}
.dbb-empty{color:#8a8a94;text-align:center;padding:34px 10px;grid-column:1/-1}
.dbb-empty .big{font-size:26px;margin-bottom:6px}
.dbb-progress{display:none;height:3px;background:#141419;overflow:hidden;position:relative;flex-shrink:0}
.dbb-progress.on{display:block}
.dbb-progress::after{content:"";position:absolute;left:-30%;width:30%;height:100%;background:#4f8cff;animation:dbb-slide 1s linear infinite}
@keyframes dbb-slide{to{left:130%}}
.dbb-footer{min-height:34px;border:1px dashed #3a3a42;border-radius:5px;padding:4px 8px;font-size:11px;color:#8a8a94;display:flex;gap:6px;align-items:center}
.dbb-footer b{color:#d8d8de}
.dbb-lightbox{position:fixed;inset:0;background:rgba(10,10,14,.82);z-index:9999;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px}
.dbb-lightbox .dbb-lb-bar{display:flex;gap:8px}
.dbb-lightbox img{max-width:92vw;max-height:84vh;border-radius:6px;box-shadow:0 6px 40px rgba(0,0,0,.6)}
.dbb-lightbox input[type=text],.dbb-lightbox textarea,.dbb-lightbox select{background:#141419;border:1px solid #3a3a42;color:#d8d8de;border-radius:5px;padding:4px 8px;outline:none;font:inherit}
.dbb-lightbox textarea{width:100%;box-sizing:border-box;resize:vertical}
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

async function apiAction(stateJson, action, mode, proxy, postId, index, outFilter) {
  const resp = await fetch(`${API_BASE}/action`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ state_json: stateJson, action, mode, post_id: postId, index, out_filter: outFilter, proxy }),
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
      <div class="dbb-progress" id="dbb-progress"></div>
      <div class="dbb-row">
        <select id="dbb-site" title="站点">
          <option value="danbooru" selected>danbooru</option>
          <option value="gelbooru">gelbooru</option>
          <option value="civitai">civitai</option>
        </select>
        <button id="dbb-settings" title="API 凭据设置">⚙</button>
        <div class="dbb-searchwrap">
          <input type="text" id="dbb-search" placeholder="标签搜索(逗号分隔)…">
          <div class="dbb-ac" id="dbb-ac"></div>
        </div>
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
        <button id="dbb-list-view" title="查看输出列表内的图片">查看列表</button>
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
    el.querySelector("#dbb-settings").onclick = () => this.openSettings();
    el.querySelector("#dbb-site").addEventListener("change", () => {
      this.modelId = null;  // 切站清模型
      this.applySiteCapabilities();
    });
    this.applySiteCapabilities();
    this.page = 1;
    this.hasNext = false;
    this.multiRating = true;
    this.capSeq = 0;
    this.modelId = null;
    this.isModelSearch = false;
    this.prefetched = new Map();  // 下一页预取任务:复用帖子响应,不只预热缩略图
    this._stateJson = null;  // 会话解析缓存(getState)
    this._state = null;
    this.progressEl = el.querySelector("#dbb-progress");
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
      const state = this.getState();
      const sel = state?.selection;
      if (sel == null) return this.setError("先选中一张帖子再插入");
      if ((state?.outlist || []).includes(sel)) return this.setError("该帖已在列表中");
      const pos = Number(el.querySelector("#dbb-list-pos").value.trim());
      this.listAction("insert_to_list", sel, Number.isInteger(pos) && pos >= 1 ? pos - 1 : 0);
    };
    this.listClearBtn.onclick = () => this.listAction("clear_list");
    this.listView = false;  // 列表视图(临时):网格只显示输出列表内帖子
    this.listViewBtn = el.querySelector("#dbb-list-view");
    this.listViewBtn.onclick = () => this.toggleListView();
    this.excludeTags = "";  // 排除标签在 ⚙ 设置弹层编辑,面板状态供搜索条件使用
    this.hideVideos = false;  // 过滤视频帖(设置弹层勾选)
    this.outFilterSeq = 0;
    // 来自AnimaDex 输入:轮询到新标签 → 填入搜索框并搜索,然后清空
    const adQWidget = this.node.widgets?.find((w) => w.name === "来自AnimaDex");
    let prevAdQ = "";
    setInterval(() => {
      if (!adQWidget || !this.el) return;
      const q = (adQWidget.value || "").trim();
      if (q && q !== prevAdQ) {
        prevAdQ = q;
        adQWidget.value = "";
        const siteSel = this.el.querySelector("#dbb-site");
        if (siteSel && this.isModelSearch) siteSel.value = "danbooru";  // 标签搜不了模型
        const input = this.el.querySelector("#dbb-search");
        if (input) input.value = q;
        this.applySiteCapabilities().then(() => this.doSearch());
      }
    }, 500);
    this.hasExcludeTags = true;  // 能力旗标:applySiteCapabilities 更新
    this.promptIsEmbedded = false;
    el.querySelectorAll(".dbb-chip").forEach((c) => {
      c.onclick = () => {
        if (this.multiRating === false) {
          // 站点评级单选(如 gelbooru 无 OR 运算):点选即唯一选中;
          // 点已选中的清空(空 = 全部不过滤,可回到无筛选)
          if (c.classList.contains("on")) {
            c.classList.remove("on");
          } else {
            el.querySelectorAll(".dbb-chip").forEach((x) => x.classList.remove("on"));
            c.classList.add("on");
          }
          return;
        }
        // 多选:至少保留一个评级(全关 = 不过滤,语义不清)
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
    const state = this.getState();
    if (state?.conditions) {
      this.syncControls(state);
      // 先拉站点能力(决定搜索框模式:标签 vs 模型),再重拉结果
      this.applySiteCapabilities().then(() => {
        if (state.page && state.page > 1) this.gotoPage(state.page);
        else this.doSearch();
      });
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
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") this.doSearch();
    });
    input.addEventListener("input", () => {
      clearTimeout(timer);
      if (this.isModelSearch) this.modelId = null;  // 编辑输入 = 放弃已选模型
      const q = input.value.trim();
      if (!q) return hide();
      const mySeq = ++seq;
      timer = setTimeout(async () => {
        try {
          if (this.isModelSearch) {
            // civitai:模型名搜索 → 选择器,选中即按模型浏览图片
            const resp = await fetch(`${API_BASE}/models?q=${encodeURIComponent(q)}`);
            const data = await resp.json();
            if (mySeq !== seq) return;
            if (data.error || !data.models?.length) return hide();
            box.innerHTML = "";
            data.models.slice(0, 8).forEach((m) => {
              const div = document.createElement("div");
              div.textContent = m.name;
              div.onmousedown = () => {
                this.modelId = m.id;
                input.value = m.name;
                hide();
                this.doSearch();
              };
              box.appendChild(div);
            });
            box.style.display = "block";
            return;
          }
          const resp = await fetch(`${API_BASE}/tags?q=${encodeURIComponent(q)}`);
          const data = await resp.json();
          if (mySeq !== seq) return;
          if (data.error || !data.tags?.length) return hide();
          box.innerHTML = "";
          data.tags.slice(0, 8).forEach((t) => {
            const div = document.createElement("div");
            div.textContent = t.cn ? `${t.tag}(${t.cn})` : t.tag;  // 中文别名补全显示「标签(中文)」
            div.onmousedown = () => {
              // 补全语义:替换正在输入的最后一段,而不是追加
              const words = input.value.trim().split(/[,\s]+/).filter(Boolean);
              if (words.length) words[words.length - 1] = t.tag;
              else words.push(t.tag);
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
    const ratings = [...this.el.querySelectorAll(".dbb-chip.on")].map((c) => c.dataset.r);
    const base = {
      site: this.el.querySelector("#dbb-site").value,
      ratings,
      sort: this.el.querySelector("#dbb-sort").value,
      per_page: +this.el.querySelector("#dbb-perpage").value,
      hide_videos: this.hideVideos,
    };
    if (this.isModelSearch) {  // civitai:按模型浏览,无标签体系
      return { ...base, model_id: this.modelId };
    }
    const tags = this.el.querySelector("#dbb-search").value.trim().split(/[,\s]+/).filter(Boolean);
    const excludeTags = (this.excludeTags || "").trim().split(/[,\s]+/).filter(Boolean);
    return { ...base, tags, exclude_tags: excludeTags };
  }

  syncControls(state) {
    const c = state?.conditions || {};
    const siteSel = this.el.querySelector("#dbb-site");
    if (c.site && siteSel.value !== c.site) siteSel.value = c.site;  // 还原站点选择
    this.modelId = c.model_id ?? null;  // civitai:还原模型
    this.hideVideos = !!c.hide_videos;  // 过滤视频帖(设置弹层勾选)
    this.excludeTags = (c.exclude_tags || []).join(", ");
    this.el.querySelector("#dbb-search").value = (c.tags || []).join(", ");
    this.el.querySelectorAll(".dbb-chip").forEach((chip) => {
      chip.classList.toggle("on", (c.ratings || ALL_RATINGS).includes(chip.dataset.r));
    });
    this.el.querySelector("#dbb-sort").value = c.sort || "new";
    this.el.querySelector("#dbb-perpage").value = String(c.per_page || 40);
  }

  async doSearch() {
    this.setError("");
    this.progressEl?.classList.add("on");  // 加载进度条
    this.clearPrefetch();  // 新搜索 = 新的结果身份,旧的预取记录作废
    try {
      // 模型模式:未从下拉选择时,自动选中第一个模型结果
      if (this.isModelSearch && !this.modelId) {
        const q = this.el.querySelector("#dbb-search").value.trim();
        if (!q) return this.setError("civitai 需要先选择模型:搜索模型名 → 选择模型");
        const resp = await fetch(`${API_BASE}/models?q=${encodeURIComponent(q)}`);
        const data = await resp.json();
        if (data.error || !data.models?.length) return this.setError("没有找到匹配的模型");
        this.modelId = data.models[0].id;
        this.el.querySelector("#dbb-search").value = data.models[0].name;
      }
      const conditions = this.readConditions();
      const res = await apiSearch(this.widget?.value || "", conditions, this.proxyWidget?.value || "");
      if (res.error) {
        this.setError(res.error);
        return;
      }
      this.applyResult(res);
    } catch (e) {
      this.setError(`搜索失败: ${e.message || e}`);
    } finally {
      this.progressEl?.classList.remove("on");
    }
  }

  async gotoPage(n) {
    this.setError("");
    this.progressEl?.classList.add("on");
    try {
      const stateJson = this.widget?.value || "";
      const prefetched = this.prefetched.get(n);
      // 预取以同一份会话为基线时可直接复用;选择/模式等状态变化后则正常重拉,
      // 避免用旧 state_json 覆盖用户刚完成的操作。
      let request;
      if (prefetched?.stateJson === stateJson) {
        request = prefetched.start();
      } else {
        if (prefetched?.timer) clearTimeout(prefetched.timer);
        request = apiPage(stateJson, n, this.proxyWidget?.value || "");
      }
      this.prefetched.delete(n);
      const res = await request;
      if (res.error) {
        this.setError(res.error);
        return;
      }
      this.applyResult(res);
    } catch (e) {
      this.setError(`翻页失败: ${e.message || e}`);
    } finally {
      this.progressEl?.classList.remove("on");
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

  async listAction(action, postId, index, outFilter, seq) {
    this.setError("");
    try {
      const res = await apiAction(
        this.widget?.value || "", action, undefined, this.proxyWidget?.value || "", postId, index, outFilter,
      );
      if (res.error) {
        this.setError(res.error);
        return;
      }
      if (seq !== undefined && seq !== this.outFilterSeq) return;  // 过期响应不覆盖新状态
      this.applyStateOnly(res.state_json);
    } catch (e) {
      this.setError(`列表操作失败: ${e.message || e}`);
    }
  }

  toggleListView() {
    this.listView = !this.listView;
    this.listViewBtn.textContent = this.listView ? "退出列表" : "查看列表";
    const state = this.getState();
    if (this.listView) {
      this.renderListView(state);
    } else {
      // 退出视图:恢复当前页搜索结果网格(不重拉,页码/选中保持)
      const curPage = this.currentPage(state);
      if (!curPage?.posts?.length) this.renderEmpty("没有符合条件的帖子");
      else {
        this.renderGrid(curPage.posts, new Set(state?.failed || []), this.currentOutputId(state));
        this.applySelectionHighlight(state);
      }
    }
  }

  currentPage(state) {
    return (state?.pages || []).find((pg) => pg.number === (this.page || 1));
  }

  currentOutputId(state) {
    return state?.mode !== "manual" ? state.last_output : null;  // 手动模式无红标
  }

  getState() {
    // 会话 JSON 随翻页/自动模式增长到多 MB,重复 parse 是面板卡顿主因;
    // widget 值未变时复用上次解析结果(值变更后首次访问重新解析)
    const value = this.widget?.value;
    if (this._stateJson === value) return this._state;
    this._stateJson = value;
    this._state = parseWidget(value);
    return this._state;
  }

  adoptState(stateJson, state = parseWidget(stateJson)) {
    // 写 widget 与更新解析缓存必须是一个操作;否则同一状态会在后续 renderFooter
    // 中再 parse 一遍,大工作流执行后会产生可见停顿。
    this.widget.value = stateJson;
    this._stateJson = stateJson;
    this._state = state;
    return state;
  }

  thumbUrl(url) {
    return `${API_BASE}/image?url=${encodeURIComponent(url)}`;
  }

  prefetchNextPage() {
    if (!this.hasNext) return;  // 最后一页不预取
    const sort = this.getState()?.conditions?.sort;
    if (sort === "random") return;  // 随机重抽样,预取无效
    const target = this.page + 1;
    const stateJson = this.widget?.value || "";
    const old = this.prefetched.get(target);
    if (old?.stateJson === stateJson) return;  // 同一结果身份仅预取一次
    if (old?.timer) clearTimeout(old.timer);
    const job = {
      stateJson,
      promise: null,
      timer: null,
      start: () => {
        if (job.timer) clearTimeout(job.timer);
        if (!job.promise) job.promise = apiPage(stateJson, target, this.proxyWidget?.value || "");
        return job.promise;
      },
    };
    this.prefetched.set(target, job);
    job.timer = setTimeout(async () => {
      try {
        const res = await job.start();
        if (this.prefetched.get(target) !== job || this.widget?.value !== stateJson) return;
        if (res.error) {
          this.prefetched.delete(target);  // 后台失败不污染用户稍后的正常翻页重试
          return;
        }
        if (!res.posts?.length) return;
        // 帖子响应保留给 gotoPage 复用;同时预热缩略图(#20),翻页无需二次 API 请求。
        res.posts.slice(0, 15).forEach((p) => {
          if (!p.preview_url) return;
          const img = new Image();
          img.src = this.thumbUrl(p.preview_url);
        });
      } catch { /* 静默:预取失败不影响浏览 */ }
    }, 500);
  }

  clearPrefetch() {
    this.prefetched.forEach((job) => {
      if (job.timer) clearTimeout(job.timer);
    });
    this.prefetched.clear();
  }

  applySelectionHighlight(state) {
    const sel = state?.selection;
    if (sel == null) return;
    this.grid.querySelectorAll(".thumb").forEach((t) => {
      t.classList.toggle("sel", +t.dataset.id === sel);
    });
  }

  renderListView(state) {
    if (!state?.conditions) {
      this.renderEmpty("未浏览 — 先搜索再查看列表");
      return;
    }
    const posts = this.buildListViewPosts(state);
    if (!posts.length) {
      this.renderEmpty("列表为空 — 在面板中把帖子加入列表");
      return;
    }
    this.renderGrid(posts, new Set(state.failed || []), this.currentOutputId(state));
    this.applySelectionHighlight(state);
  }

  buildListViewPosts(state) {
    const posts = [];
    for (const id of state?.outlist || []) {
      const post = this.findPost(state, id);
      posts.push(post
        ? {
            id: post.id, preview_url: post.preview_url || post.file_url,
            rating: post.rating, score: post.score, animated: post.animated, loaded: true,
          }
        : { id, preview_url: "", rating: "", score: 0, animated: false, loaded: false });
    }
    return posts;
  }

  toggleListForSelection() {
    const state = this.getState();
    const sel = state?.selection;
    if (sel == null) return this.setError("先选中一张帖子再操作列表");
    const inList = (state?.outlist || []).includes(sel);
    this.listAction(inList ? "remove_from_list" : "add_to_list", sel);
  }

  applyStateOnly(stateJson) {
    const state = this.adoptState(stateJson);
    this.updateMode(state?.mode);
    this.updateStatus(state);
    this.updateListToggle(state?.selection ?? null);
    this.renderFooter(state?.selection ?? null);
    this.applyMarks(state);  // 执行后红标/失败标记即时更新(不重绘网格)
    if (this.listView) this.renderListView(state);  // 列表操作后视图即时更新
  }

  applyMarks(state) {
    const currentId = this.currentOutputId(state);
    const failedSet = new Set(state?.failed || []);
    this.grid.querySelectorAll(".thumb").forEach((t) => {
      const id = +t.dataset.id;
      t.classList.toggle("current", currentId != null && id === currentId);
      t.classList.toggle("failed", failedSet.has(id));
    });
  }

  updateMode(mode) {
    const m = mode || "manual";
    this.modeManualBtn.classList.toggle("on", m === "manual");
    this.modeAutoBtn.classList.toggle("on", m === "auto");
    this.modeListBtn.classList.toggle("on", m === "list");
    // 自动/列表模式都有重置语义(选中帖 / 列表开头),普通模式无意义
    this.resetBtn.disabled = m === "manual";
  }

  applyResult(res) {
    this.page = res.page;
    this.hasNext = !!res.has_next;
    this.multiRating = res.capabilities?.multi_rating !== false;  // 站点能力:评级多选/单选
    this.pageInput.value = res.page;
    this.updateNavButtons();
    if (this.listView) {  // 新搜索/翻页退出列表视图,展示新结果
      this.listView = false;
      this.listViewBtn.textContent = "查看列表";
    }
    const state = this.adoptState(res.state_json);
    this.renderGrid(res.posts, new Set(state?.failed || []), this.currentOutputId(state));
    this.applySelectionHighlight(state);
    if (this.isModelSearch && this.modelId) {
      // civitai:搜索框显示模型名(重开工作流时从首帖 raw 还原)
      const first = (state.pages || []).flatMap((pg) => pg.posts)[0];
      const name = first?.raw?.model?.name;
      if (name) this.el.querySelector("#dbb-search").value = name;
    }
    this.updateMode(state?.mode);
    this.updateStatus(state);
    this.renderFooter(state?.selection ?? null);
    this.prefetchNextPage();  // 后台预热下一页缩略图
  }

  updateNavButtons() {
    this.prevBtn.disabled = !this.page || this.page <= 1;
    this.nextBtn.disabled = !this.hasNext;
  }

  renderGrid(posts, failedSet, currentId) {
    if (!posts?.length) {
      this.renderEmpty("没有符合条件的帖子");
      return;
    }
    this.grid.innerHTML = posts
      .map(
        (p, i) => p.loaded === false
          ? `<div class="thumb placeholder" data-id="${p.id}" title="#${p.id} · 不在已加载结果中,可选中后从列表移除">#${p.id}</div>`
          : `
      <div class="thumb${failedSet?.has(p.id) ? " failed" : ""}${currentId != null && p.id === currentId ? " current" : ""}" data-id="${p.id}" title="#${p.id} · ${RATING_LABEL[p.rating] || p.rating} · ★${p.score}">
        ${failedSet?.has(p.id) ? '<span class="fail-badge">✕</span>' : ""}
        <span class="badge" style="background:${RATING_COLOR[p.rating] || "#666"}">${p.id}</span>
        <img src="${this.thumbUrl(p.preview_url)}" alt="#${p.id}" loading="${i < 12 ? "eager" : "lazy"}" referrerpolicy="no-referrer" onerror="this.style.visibility='hidden'">
      </div>`,
      )
      .join("");
    this.grid.querySelectorAll(".thumb").forEach((t) => {
      t.onclick = () => this.selectPost(+t.dataset.id);
      // 双击:两次单击的 toggle 互相抵消,选中状态不变,可安全共存
      t.ondblclick = () => this.showLightbox(+t.dataset.id);
    });
  }

  findPost(state, id) {
    const p = (state.pages || []).flatMap((pg) => pg.posts).find((p) => p.id === id);
    if (p) return p;
    // 换站/翻页后旧帖不在已加载页:回退会话快照(加入列表时存的完整数据)
    return state?.list_cache?.[String(id)] || null;
  }

  showLightbox(id) {
    const state = this.getState();
    if (!state) return;
    const post = this.findPost(state, id);
    if (!post) return;
    // 归一化字段:适配器已把各站预览/大图/原图映射到 Post(ADR-0003)
    const sample = post.sample_url || post.preview_url || post.file_url;
    const original = post.file_url;
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
      img.src = this.thumbUrl(url);
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
    // gif 可在浏览器显示;webm/swf/mp4 视频按动画提示(mp4 的扩展名在 URL 里)
    if (post.animated && !String(sample).toLowerCase().endsWith(".gif")) {
      toggle.disabled = true;
      fail("动画帖(视频),暂不支持大图预览");
      return;
    }
    if (!hasOriginal) toggle.disabled = true;  // 原图不可用时切换是 no-op
    load(sample, "原图");
  }

  renderEmpty(msg) {
    this.grid.innerHTML = `<div class="dbb-empty"><div class="big">🔍</div>${msg}</div>`;
  }

  selectPost(id) {
    const state = this.getState();
    if (!state || !state.pages) return;
    state.selection = state.selection === id ? null : id;  // 选中只是标记,不移动游标
    this.adoptState(JSON.stringify(state), state);
    this.grid.querySelectorAll(".thumb").forEach((t) => {
      t.classList.toggle("sel", +t.dataset.id === state.selection);
    });
    this.updateStatus(state);
    this.renderFooter(state.selection);
  }

  renderFooter(selId) {
    const text = this.el.querySelector("#dbb-footer-text");
    const state = this.getState();
    if (!state || selId == null) {
      text.textContent = "未选中 — 点击缩略图选中;执行队列输出所选帖子";
      this.updateListToggle(null);
      return;
    }
    const post = this.findPost(state, selId);
    if (post) {
      if (this.isModelSearch) {
        // civitai:内嵌提示词;缺失时提示
        const prompt = post.raw?.meta?.prompt || "";
        text.innerHTML = prompt
          ? `已选 <b>#${post.id}</b> · 提示词:${prompt}`
          : `已选 <b>#${post.id}</b> · 无内嵌提示词`;
      } else {
        // 与后端派生一致:输出过滤剔除的标签在预览中同样剔除
        const filter = state?.out_filter || [];
        const filtered = post.tags.filter((t) => !filter.includes(t));
        text.innerHTML = filtered.length
          ? `已选 <b>#${post.id}</b> · 提示词:${filtered.join(", ")}`
          : `已选 <b>#${post.id}</b> · 提示词已全部被过滤`;
      }
    } else {
      text.innerHTML = `已选 <b>#${selId}</b>`;
    }
    this.updateListToggle(selId);
  }

  async applySiteCapabilities() {
    const mySeq = ++this.capSeq;  // 快速切站时丢弃过期响应
    const site = this.el.querySelector("#dbb-site").value;
    try {
      const resp = await fetch(`${API_BASE}/capabilities?site=${encodeURIComponent(site)}`);
      const data = await resp.json();
      if (mySeq !== this.capSeq) return;
      if (data.multi_rating !== undefined) this.multiRating = data.multi_rating !== false;
      if (!this.multiRating) {
        const on = this.el.querySelectorAll(".dbb-chip.on");
        on.forEach((x, i) => { if (i > 0) x.classList.remove("on"); });  // 只保留第一个
      }
      this.hasExcludeTags = data.has_exclude_tags !== false;
      this.promptIsEmbedded = data.prompt_kind === "embedded";
      const sortOpts = data.sort_options || ["new", "score", "random"];
      const sortSel = this.el.querySelector("#dbb-sort");
      [...sortSel.options].forEach((o) => {
        o.disabled = !sortOpts.includes(o.value);
        if (o.disabled && sortSel.value === o.value) sortSel.value = "new";
      });
      this.isModelSearch = data.has_model_search === true;
      const searchInput = this.el.querySelector("#dbb-search");
      searchInput.placeholder = this.isModelSearch ? "模型名搜索…" : "标签搜索(逗号分隔)…";
    } catch { /* 搜索时会再同步 */ }
  }

  openSettings() {
    // 凭据设置:仅写本地 credentials.json,绝不进工作流 JSON(T10)
    const overlay = document.createElement("div");
    overlay.className = "dbb-lightbox";
    overlay.innerHTML = `
      <div class="dbb-lb-bar"><b>凭据设置</b><button class="dbb-lb-close">关闭</button></div>
      <div style="display:flex;flex-direction:column;gap:10px;background:#141419;border:1px solid #3a3a42;border-radius:8px;padding:16px;min-width:460px;max-width:92vw">
        <div><b>danbooru</b> <span style="color:#8a8a94;font-size:11px">(可选,匿名可用)</span><button class="dbb-cred-clear" data-site="danbooru" style="margin-left:8px">清除</button></div>
        <div style="display:flex;gap:6px">
          <input id="dbb-cred-dan-login" placeholder="登录名" style="flex:1">
          <input id="dbb-cred-dan-key" placeholder="api_key" style="flex:2">
        </div>
        <div><b>gelbooru</b> <span style="color:#8a8a94;font-size:11px">(必填)</span><button class="dbb-cred-clear" data-site="gelbooru" style="margin-left:8px">清除</button></div>
        <div style="display:flex;gap:6px">
          <input id="dbb-cred-gel-uid" placeholder="user_id" style="flex:1">
          <input id="dbb-cred-gel-key" placeholder="api_key" style="flex:2">
        </div>
        <button class="dbb-cred-save" style="background:#4f8cff;border:none;color:#fff;border-radius:5px;padding:5px">保存</button>
        <div class="dbb-cred-status" style="color:#8a8a94;font-size:11px">留空 = 保持不变;清除需编辑 credentials.json</div>
        <hr style="border:none;border-top:1px solid #3a3a42;margin:4px 0">
        <div><b>搜索与输出</b></div>
        <div style="display:flex;flex-direction:column;gap:4px">
          <span style="color:#8a8a94;font-size:11px">排除标签(逗号分隔,含任一排除标签的帖子不出现)</span>
          <textarea id="dbb-set-exclude" rows="2" placeholder="如: nude, blood"></textarea>
        </div>
        <div style="display:flex;flex-direction:column;gap:4px">
          <span style="color:#8a8a94;font-size:11px">输出过滤(逗号分隔,提示词输出时剔除的标签)</span>
          <textarea id="dbb-set-outfilter" rows="2" placeholder="如: nsfw, text"></textarea>
        </div>
        <label style="display:flex;gap:6px;align-items:center;font-size:11px;color:#d8d8de;cursor:pointer">
          <input type="checkbox" id="dbb-set-hidevideos"> 过滤视频帖
        </label>
      </div>
    `;
    const inputs = {
      danbooru: [overlay.querySelector("#dbb-cred-dan-login"), overlay.querySelector("#dbb-cred-dan-key")],
      gelbooru: [overlay.querySelector("#dbb-cred-gel-uid"), overlay.querySelector("#dbb-cred-gel-key")],
    };
    // 搜索与输出:排除标签为面板状态(参与下次搜索条件);输出过滤实时同步会话
    const excludeInput = overlay.querySelector("#dbb-set-exclude");
    const outfilterInput = overlay.querySelector("#dbb-set-outfilter");
    excludeInput.value = this.excludeTags || "";
    excludeInput.disabled = !this.hasExcludeTags;  // civitai 无标签体系
    excludeInput.addEventListener("input", () => { this.excludeTags = excludeInput.value; });
    outfilterInput.value = (this.getState()?.out_filter || []).join(", ");
    outfilterInput.disabled = this.promptIsEmbedded;  // 内嵌提示词不适用
    const hideVideosInput = overlay.querySelector("#dbb-set-hidevideos");
    hideVideosInput.checked = !!this.hideVideos;
    hideVideosInput.addEventListener("change", () => { this.hideVideos = hideVideosInput.checked; });
    let ofTimer = null;
    outfilterInput.addEventListener("input", () => {
      clearTimeout(ofTimer);
      const mySeq = ++this.outFilterSeq;
      ofTimer = setTimeout(() => {
        const tags = outfilterInput.value.trim().split(/[,\s]+/).filter(Boolean);
        this.listAction("set_out_filter", undefined, undefined, tags, mySeq);
      }, 300);
    });
    const status = overlay.querySelector(".dbb-cred-status");
    const refresh = async () => {
      for (const [site, pair] of Object.entries(inputs)) {
        try {
          const resp = await fetch(`${API_BASE}/credentials?site=${site}`);
          const data = await resp.json();
          pair.forEach((input) => {
            input.placeholder = data.configured ? "已配置,留空保持" : input.getAttribute("data-base") || input.placeholder;
          });
        } catch { /* 忽略 */ }
      }
    };
    const close = () => {
      clearTimeout(ofTimer);  // 关闭即取消未触发的防抖,重开不显示陈旧值
      overlay.remove();
      document.removeEventListener("keydown", onKey);
    };
    const onKey = (e) => { if (e.key === "Escape") close(); };
    overlay.querySelector(".dbb-lb-close").onclick = close;
    overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });
    document.addEventListener("keydown", onKey);
    overlay.querySelectorAll(".dbb-cred-clear").forEach((btn) => {
      btn.onclick = async () => {
        try {
          const resp = await fetch(`${API_BASE}/credentials`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ site: btn.dataset.site, action: "clear" }),
          });
          const data = await resp.json();
          if (data.error) throw new Error(data.error);
          status.textContent = `已清除 ${btn.dataset.site} 的凭据`;
          refresh();
        } catch (e) {
          status.textContent = `清除失败: ${e.message || e}`;
        }
      };
    });
    overlay.querySelector(".dbb-cred-save").onclick = async () => {
      const jobs = [
        ["danbooru", { login: inputs.danbooru[0].value.trim(), api_key: inputs.danbooru[1].value.trim() }],
        ["gelbooru", { user_id: inputs.gelbooru[0].value.trim(), api_key: inputs.gelbooru[1].value.trim() }],
      ];
      try {
        for (const [site, fields] of jobs) {
          const resp = await fetch(`${API_BASE}/credentials`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ site, fields }),
          });
          const data = await resp.json();
          if (data.error) throw new Error(data.error);
        }
        status.textContent = "已保存(无需重启,立即生效)";
        inputs.danbooru.forEach((i) => { i.value = ""; });
        inputs.gelbooru.forEach((i) => { i.value = ""; });
        refresh();
      } catch (e) {
        status.textContent = `保存失败: ${e.message || e}`;
      }
    };
    document.body.appendChild(overlay);
    refresh();
  }

  updateListToggle(selId) {
    const state = this.getState();
    const inList = selId != null && (state?.outlist || []).includes(selId);
    this.listToggleBtn.textContent = inList ? "从列表移除" : "加入列表";
  }

  updateStatus(state) {
    const modeLabel = { manual: "普通", auto: "自动", list: "列表" }[state?.mode] || "普通";
    const sel = state?.selection != null ? `#${state.selection}` : "—";
    // 手动:游标是当前页内的位置;自动:游标跨全部已加载;列表:游标对列表长度
    const curPage = this.currentPage(state);
    const total = (state?.pages || []).reduce((n, pg) => n + pg.posts.length, 0);
    const nPosts = state?.mode === "auto" ? total : (curPage ? curPage.posts.length : 0);
    const maxN = state?.mode === "list" ? (state.outlist || []).length : nPosts;
    const cur = state?.cursor != null
      ? `${Math.min(state.cursor, maxN)}/${maxN}`  // 越界游标(重开结果变少)显示钳制
      : "—";
    const nList = state?.outlist?.length || 0;
    const nFailed = state?.failed?.length || 0;
    this.statusText.innerHTML = `${modeLabel} · 游标 <b>${cur}</b> · 已选 <b>${sel}</b> · 列表 <b>${nList}</b> · 失败 <b>${nFailed}</b>`;
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
