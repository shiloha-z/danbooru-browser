import { app } from "../../scripts/app.js";

const API_BASE = "/danbooru_browser";

/**
 * AnimaDex 角色/画师浏览器(移植自参考包,issue #25)。
 *
 * 搜索/分面筛选/翻页/随机;点击卡片选中,复制标签,「去 D站搜索」
 * 把标签写入 DanbooruBrowserNode 的搜索框并输出到 _tag。
 */

app.registerExtension({
  name: "DanbooruBrowser.AnimaDex",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== "DanbooruBrowserAnimaDex") return;
    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      onNodeCreated?.apply(this, arguments);
      this.setSize([800, 1020]);
      this.title = "AnimaDex 浏览器";
      this.isChanged = true;
      const node = this;

      // _tag widget 隐藏(20px 高度保留端口可见)
      const tagW = node.widgets?.find((w) => w.name === "_tag");
      if (tagW) { tagW.computeSize = () => [0.1, 20]; tagW.serialize = true; }

      let mode = "artists";
      let sortMode = "count";
      let results = [];
      let filters = {};
      let facetData = {};
      let page = 1;
      let totalResults = 0;
      const PAGE_SIZE = 36;

      const el = document.createElement("div");
      el.style.cssText = "width:100%;height:100%;display:flex;flex-direction:column;background:#1a1a2e;border-radius:6px;min-height:0;";

      // ── 顶栏 ──
      const bar = document.createElement("div");
      bar.style.cssText = "display:flex;gap:6px;padding:8px;align-items:center;border-bottom:1px solid #0f3460;flex-shrink:0;position:relative;flex-wrap:wrap;";

      const btns = {};
      for (const [mk, ml] of [["artists", "🎨 画师"], ["characters", "👤 角色"]]) {
        const b = document.createElement("button");
        b.textContent = ml;
        b.style.cssText = `padding:5px 12px;border-radius:4px;border:none;cursor:pointer;font-size:12px;font-weight:bold;background:${mk === mode ? "#e94560" : "#2a2a3a"};color:${mk === mode ? "#fff" : "#aaa"};`;
        b.onclick = () => {
          mode = mk;
          filters = {};
          page = 1;
          for (const [k, v] of Object.entries(btns)) {
            v.style.background = k === mode ? "#e94560" : "#2a2a3a";
            v.style.color = k === mode ? "#fff" : "#aaa";
          }
          inp.placeholder = mk === "characters" ? "搜索角色名..." : "搜索画师名...";
          loadFacets();
          if (inp.value.trim()) { clearTimeout(_searchTimer); search(); }
          else doSearch("");
        };
        btns[mk] = b;
        bar.appendChild(b);
      }

      // ── 排序/随机 ──
      const sortBtns = {};
      for (const [sk, sl] of [["count", "🔥 热门"], ["fav_count", "❤️ 最多喜欢"], ["random", "🔀 随机"]]) {
        const sb = document.createElement("button");
        sb.textContent = sl;
        sb.style.cssText = `padding:5px 8px;border-radius:4px;border:none;cursor:pointer;font-size:11px;background:${sk === sortMode ? "#0f3460" : "transparent"};color:${sk === sortMode ? "#4fc3f7" : "#888"};`;
        sb.onclick = () => {
          sortMode = sk;
          page = 1;
          for (const [k, v] of Object.entries(sortBtns)) {
            v.style.background = k === sortMode ? "#0f3460" : "transparent";
            v.style.color = k === sortMode ? "#4fc3f7" : "#888";
          }
          if (inp.value.trim()) { clearTimeout(_searchTimer); search(); }
          else doSearch("");
        };
        sortBtns[sk] = sb;
        bar.appendChild(sb);
      }

      const inp = document.createElement("input");
      inp.type = "text";
      inp.placeholder = "搜索画师名...";
      inp.style.cssText = "flex:1;min-width:120px;padding:6px 10px;border-radius:4px;border:1px solid #0f3460;background:#16213e;color:#e0e0e0;font-size:13px;outline:none;";

      // ── 自动补全 ──
      const acList = document.createElement("div");
      acList.style.cssText = "display:none;position:absolute;top:100%;left:0;right:0;background:#1a1a2e;border:1px solid #0f3460;border-radius:0 0 4px 4px;max-height:240px;overflow-y:auto;z-index:999;";
      let _acTimer = null;
      let _searchTimer = null;

      function showAc(items) {
        acList.innerHTML = "";
        if (!items || !items.length) { acList.style.display = "none"; return; }
        for (const r of items) {
          const row = document.createElement("div");
          const name = r.name || "";
          const cp = r.copyright_name || "";
          row.style.cssText = "padding:5px 8px;cursor:pointer;color:#b0bec5;font-size:12px;border-bottom:1px solid #0f3460;display:flex;gap:6px;align-items:center;";
          row.onmouseover = () => { row.style.background = "#0d2137"; };
          row.onmouseout = () => { row.style.background = "transparent"; };
          row.onclick = () => {
            inp.value = name;
            acList.style.display = "none";
            page = 1;
            doSearch(name);
          };
          const nm = document.createElement("span");
          nm.textContent = name;
          nm.style.cssText = "font-weight:bold;color:#e0e0e0;font-size:12px;";
          row.appendChild(nm);
          if (cp) {
            const sc = document.createElement("span");
            sc.textContent = cp;
            sc.style.cssText = "color:#888;font-size:10px;margin-left:auto;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:120px;";
            row.appendChild(sc);
          }
          acList.appendChild(row);
        }
        acList.style.display = "block";
      }

      inp.oninput = () => {
        const q = inp.value.trim();
        if (!q) { acList.style.display = "none"; clearTimeout(_searchTimer); return; }
        clearTimeout(_acTimer);
        _acTimer = setTimeout(async () => {
          if (acList.style.display === "none" || acList.innerHTML === "") {
            acList.innerHTML = '<div style="padding:8px;text-align:center;color:#666;font-size:11px;">⏳ 搜索建议...</div>';
            acList.style.display = "block";
          }
          try {
            const r = await fetch(`${API_BASE}/animadex/search`, {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ mode, query: q, page: 1 }),
            });
            const d = await r.json();
            showAc((d.results || []).slice(0, 10));
          } catch { acList.style.display = "none"; }
        }, 150);
      };
      inp.onkeydown = (e) => {
        if (e.key === "Enter") { acList.style.display = "none"; clearTimeout(_searchTimer); search(); }
        if (e.key === "Escape") acList.style.display = "none";
      };
      inp.onblur = () => setTimeout(() => { acList.style.display = "none"; }, 200);

      const sBtn = document.createElement("button");
      sBtn.textContent = "🔍";
      sBtn.style.cssText = "padding:5px 14px;border-radius:4px;border:none;background:#e94560;color:#fff;cursor:pointer;font-size:16px;";
      sBtn.onclick = search;
      bar.append(inp, acList, sBtn);

      // ── 分面筛选(键为 animadex API 原生英文 facet 键) ──
      const LABELS = {
        character: "角色", copyright: "版权", gender: "性别",
        hair_color: "发色", hair_length: "发长", eye_color: "瞳色",
        species: "种族", occupation: "职业", nationality: "国籍",
        media: "媒体", artist: "画师", breed: "种族",
      };
      const filterBar = document.createElement("div");
      filterBar.style.cssText = "display:none;flex-wrap:wrap;gap:4px;padding:4px 8px;border-bottom:1px solid #0f3460;flex-shrink:0;font-size:11px;align-items:center;";

      function renderFilters() {
        filterBar.innerHTML = "";
        const facets = facetData[mode];
        if (!facets) return;
        for (const [key, f] of Object.entries(facets)) {
          // facet 结构:{label, total, values: [{value, label, count}]}(实测)
          const values = f?.values;
          if (!values || !values.length) continue;
          const wrap = document.createElement("div");
          wrap.style.cssText = "display:flex;gap:3px;align-items:center;padding:2px 4px;border:1px solid #0f3460;border-radius:4px;";
          const lab = document.createElement("span");
          lab.textContent = f.label || LABELS[key] || key;
          lab.style.cssText = "color:#888;";
          wrap.appendChild(lab);
          const sel = document.createElement("select");
          sel.style.cssText = "background:#16213e;color:#e0e0e0;border:none;outline:none;font-size:11px;";
          const empty = document.createElement("option");
          empty.value = "";
          empty.textContent = "全部";
          sel.appendChild(empty);
          for (const v of values) {
            const val = typeof v === "object" ? (v.value ?? "") : v;
            const o = document.createElement("option");
            o.value = val;
            o.textContent = val;
            sel.appendChild(o);
          }
          sel.value = filters[key] || "";
          sel.onchange = () => {
            filters[key] = sel.value || "";
            page = 1;
            const q = inp.value.trim();
            if (q) search(); else doSearch("");
          };
          wrap.appendChild(sel);
          filterBar.appendChild(wrap);
        }
        const clear = document.createElement("button");
        clear.textContent = "✕ 清除";
        clear.style.cssText = "padding:2px 8px;border:none;border-radius:3px;background:#3a1a1a;color:#e94560;cursor:pointer;font-size:10px;";
        clear.onclick = () => {
          filters = {};
          page = 1;
          renderFilters();
          const q = inp.value.trim();
          if (q) search(); else doSearch("");
        };
        filterBar.appendChild(clear);
      }

      async function loadFacets() {
        try {
          const r = await fetch(`${API_BASE}/animadex/facets`, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ mode }),
          });
          const d = await r.json();
          if (d.success) facetData[mode] = d.facets;
        } catch {}
        renderFilters();
      }

      // ── 提示栏 + 网格 + 页码 ──
      const hint = document.createElement("div");
      hint.style.cssText = "padding:4px 10px;font-size:11px;color:#888;border-bottom:1px solid #0f3460;flex-shrink:0;display:flex;justify-content:space-between;";
      const hintLeft = document.createElement("span");
      hintLeft.textContent = "💡 点击结果选中并输出";
      const hintRight = document.createElement("span");
      hintRight.textContent = "🔽 筛选";
      hintRight.style.cssText = "cursor:pointer;color:#e94560;font-size:10px;";
      let filterVisible = false;
      hintRight.onclick = () => {
        filterVisible = !filterVisible;
        filterBar.style.display = filterVisible ? "flex" : "none";
        hintRight.textContent = filterVisible ? "🔼 收起" : "🔽 筛选";
      };
      hint.append(hintLeft, hintRight);

      const grid = document.createElement("div");
      grid.style.cssText = "flex:1;min-height:0;overflow-y:auto;padding:6px;display:flex;flex-wrap:wrap;gap:6px;align-content:flex-start;";

      const pageBar = document.createElement("div");
      pageBar.style.cssText = "display:none;justify-content:center;align-items:center;gap:8px;padding:6px 8px;border-top:1px solid #0f3460;flex-shrink:0;font-size:12px;";

      function goPage(p) {
        page = p;
        const q = inp.value.trim();
        if (q) doSearch(q); else doSearch("");
      }

      function renderPage(total) {
        totalResults = total;
        const totalPages = Math.ceil(totalResults / PAGE_SIZE);
        if (totalPages <= 1) { pageBar.style.display = "none"; return; }
        pageBar.style.display = "flex";
        pageBar.innerHTML = "";
        const prev = document.createElement("span");
        prev.textContent = "◀ 上一页";
        prev.style.cssText = `cursor:${page > 1 ? "pointer" : "default"};color:${page > 1 ? "#4fc3f7" : "#444"};font-size:11px;`;
        if (page > 1) prev.onclick = () => goPage(page - 1);
        pageBar.appendChild(prev);
        const start = Math.max(1, page - 2);
        const end = Math.min(totalPages, page + 2);
        if (start > 1) { const e = document.createElement("span"); e.textContent = "..."; e.style.cssText = "color:#666;font-size:11px;"; pageBar.appendChild(e); }
        for (let i = start; i <= end; i++) {
          const pn = document.createElement("span");
          pn.textContent = i;
          pn.style.cssText = `cursor:pointer;padding:1px 7px;border-radius:3px;font-size:11px;background:${i === page ? "#e94560" : "transparent"};color:${i === page ? "#fff" : "#aaa"};`;
          if (i !== page) pn.onclick = () => goPage(i);
          pageBar.appendChild(pn);
        }
        if (end < totalPages) { const e = document.createElement("span"); e.textContent = "..."; e.style.cssText = "color:#666;font-size:11px;"; pageBar.appendChild(e); }
        const next = document.createElement("span");
        next.textContent = "下一页 ▶";
        next.style.cssText = `cursor:${page < totalPages ? "pointer" : "default"};color:${page < totalPages ? "#4fc3f7" : "#444"};font-size:11px;`;
        if (page < totalPages) next.onclick = () => goPage(page + 1);
        pageBar.appendChild(next);
      }

      function render() {
        grid.innerHTML = "";
        if (!results.length) {
          pageBar.style.display = "none";
          grid.innerHTML = '<div style="width:100%;text-align:center;padding:60px 20px;color:#888;"><div style="font-size:48px;margin-bottom:12px;">🔍</div><div style="font-size:15px;color:#aaa;">输入关键词搜索 AnimaDex</div></div>';
          return;
        }
        for (const r of results) {
          const name = r.name || "";
          const slug = r.slug || "";
          const cp = r.copyright_name || "";
          const trig = r.trigger || "";
          const tags = r.tags || [];
          const thumbUrl = r.thumb_url || "";
          const dbTag = slug || trig || name;

          // 直连 Danbooru Browser 节点(参考包同款):连线值只在队列执行时
          // 传播,选中必须即时驱动。写入「来自AnimaDex」widget,浏览器面板
          // 轮询到新值后填入搜索框并搜索(自动处理 civitai 切回 danbooru)。
          const sendToDanbooru = (tag) => {
            if (tagW) tagW.value = tag;
            node.isChanged = true;
            for (const n of (app.graph?._nodes || [])) {
              if (n.type !== "DanbooruBrowserNode") continue;
              const aw = n.widgets?.find((w) => w.name === "来自AnimaDex");
              if (aw) aw.value = tag;
            }
          };

          const card = document.createElement("div");
          card.style.cssText = "background:#0f3460;border-radius:6px;overflow:hidden;cursor:pointer;border:2px solid transparent;width:calc(33.333% - 6px);flex-shrink:0;box-sizing:border-box;";
          card.onclick = () => {
            grid.querySelectorAll(".ad-sel").forEach((c) => { c.style.borderColor = "transparent"; c.classList.remove("ad-sel"); });
            card.style.borderColor = "#e94560";
            card.classList.add("ad-sel");
            sendToDanbooru(dbTag);  // 选中即输出并驱动浏览器节点搜索
          };

          const imgDiv = document.createElement("div");
          imgDiv.style.cssText = "width:100%;background:#16213e;display:flex;align-items:center;justify-content:center;";
          if (thumbUrl) {
            const img = new Image();
            img.style.cssText = "width:100%;height:auto;display:block;";
            img.src = `${API_BASE}/image?url=${encodeURIComponent(thumbUrl)}`;
            img.onerror = function () {
              this.style.display = "none";
              this.parentElement.textContent = "🖼";
              this.parentElement.style.fontSize = "28px";
              this.parentElement.style.color = "#555";
            };
            imgDiv.appendChild(img);
          } else {
            imgDiv.textContent = "🖼";
            imgDiv.style.fontSize = "28px";
            imgDiv.style.color = "#555";
          }

          const info = document.createElement("div");
          info.style.cssText = "padding:4px 6px;font-size:11px;color:#b0bec5;line-height:1.4;";
          let html = `<div style="font-weight:bold;color:#e0e0e0;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${name}</div>`;
          if (cp) html += `<div style="color:#888;font-size:10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">📺 ${cp}</div>`;
          if (mode === "characters") {
            const preview = [trig, ...tags].filter(Boolean).slice(0, 5);
            if (preview.length) html += `<div style="color:#4fc3f7;font-size:9px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-top:2px;">${preview.join(", ")}${tags.length > 5 ? "…" : ""}</div>`;
          } else if (trig && trig !== name) {
            html += `<div style="color:#4fc3f7;font-size:10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">🏷 ${trig}</div>`;
          }
          info.innerHTML = html;

          // ── 复制按钮 ──
          const btnRow = document.createElement("div");
          btnRow.style.cssText = "display:flex;gap:3px;margin-top:3px;";
          const mkCopyBtn = (label, text) => {
            const b = document.createElement("button");
            b.textContent = label;
            b.style.cssText = "flex:1;padding:3px 0;border:none;border-radius:3px;background:#e94560;color:#fff;cursor:pointer;font-size:10px;text-align:center;";
            b.onclick = (e) => {
              e.stopPropagation();
              navigator.clipboard.writeText(text).then(() => {
                b.textContent = "✅";
                setTimeout(() => { b.textContent = label; }, 1500);
              });
            };
            return b;
          };
          const copyTag = trig || name;
          if (mode === "characters") {
            btnRow.appendChild(mkCopyBtn("📋 标签", copyTag));
            btnRow.appendChild(mkCopyBtn("📋 标签+常用", [trig, ...tags].filter(Boolean).join(", ")));
          } else {
            btnRow.appendChild(mkCopyBtn("📋 复制 @" + (trig || name), "@" + (trig || name)));
          }
          info.appendChild(btnRow);

          // ── 去 D站搜索:写入我们的 DanbooruBrowserNode ──
          const dbBtn = document.createElement("button");
          dbBtn.textContent = "🔍 去 D站搜索";
          dbBtn.style.cssText = "display:block;width:100%;padding:3px 0;margin-top:2px;border:none;border-radius:3px;background:#0f3460;color:#4fc3f7;cursor:pointer;font-size:10px;text-align:center;";
          dbBtn.onclick = (e) => {
            e.stopPropagation();
            sendToDanbooru(dbTag);
            dbBtn.textContent = "✅ 已发送";
            setTimeout(() => { dbBtn.textContent = "🔍 去 D站搜索"; }, 1500);
          };
          info.appendChild(dbBtn);

          card.append(imgDiv, info);
          grid.appendChild(card);
        }
      }

      async function doSearch(q) {
        grid.innerHTML = '<div style="width:100%;text-align:center;padding:40px;color:#888;">⏳ 搜索中...</div>';
        pageBar.style.display = "none";
        try {
          const r = await fetch(`${API_BASE}/animadex/search`, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ mode, query: q, filters, page, sort: sortMode }),
          });
          const d = await r.json();
          results = d.results || [];
          renderPage(d.total || 0);
        } catch { results = []; }
        render();
      }

      function search() {
        page = 1;
        const q = inp.value.trim();
        if (q) doSearch(q);
      }

      el.append(bar, hint, filterBar, grid, pageBar);
      this.addDOMWidget("animadex_ui", "div", el, { onDraw: () => {} });
      this.setSize([800, 1020]);

      loadFacets();
      doSearch("");
    };
  },
});
