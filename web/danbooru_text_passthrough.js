import { app } from "../../scripts/app.js";

const API_BASE = "/danbooru_browser";

/**
 * 文本(透传)节点面板(移植自 Anima 包,issue #24)。
 *
 * 原文/标签双模式编辑;标签模式支持中文翻译(本地 /tags 索引)与
 * 回车直接添加;暂停模式:执行时阻塞,编辑后确认输出;使用上游
 * 输入切换(输入/内容)。裁剪:收藏/云翻译/标签配色/批量合并。
 */

app.registerExtension({
  name: "DanbooruBrowser.TextPassthrough",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== "DanbooruBrowserTextPassthrough") return;
    // 工作流恢复:widget 值在 configure 时应用,此时同步进 textarea
    const onConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
      onConfigure?.apply(this, arguments);
      if (this._pt) this._pt.syncFromWidgets();
    };
    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      onNodeCreated?.apply(this, arguments);

      const textWidget = this.widgets?.find((w) => w.name === "text");
      const promptWidget = this.widgets?.find((w) => w.name === "prompt_text");
      const useInputWidget = this.widgets?.find((w) => w.name === "use_input_text");
      if (!textWidget) return;

      const wrap = document.createElement("div");
      wrap.style.cssText = "display:flex;flex-direction:column;gap:4px;padding:6px;min-width:220px;height:100%;box-sizing:border-box;overflow-y:auto";

      const toolbar = document.createElement("div");
      toolbar.style.cssText = "display:flex;gap:4px;align-items:center;flex-wrap:wrap";
      const btnStyle = "background:#33333c;border:1px solid #3a3a42;color:#d8d8de;border-radius:5px;padding:2px 8px;cursor:pointer;font:inherit;font-size:11px";

      const modeBtn = document.createElement("button");
      modeBtn.textContent = "⬡ 标签模式";
      modeBtn.title = "切换 原文 ↔ 标签(chip)模式";
      modeBtn.style.cssText = btnStyle;

      const pauseBtn = document.createElement("button");
      let pauseMode = false;
      const setPauseBtn = () => {
        pauseBtn.textContent = pauseMode ? "⏸ 暂停 开" : "⏸ 暂停 关";
        pauseBtn.style.background = pauseMode ? "#0f3460" : "#33333c";
        pauseBtn.style.color = pauseMode ? "#4fc3f7" : "#d8d8de";
      };
      setPauseBtn();
      pauseBtn.title = "开启后执行时阻塞,编辑后点确认输出";
      pauseBtn.onclick = () => {
        pauseMode = !pauseMode;
        setPauseBtn();
        // 空格标记触发 IS_CHANGED → 重执行进入暂停流
        const pw = this.widgets?.find((w) => w.name === "prompt_text");
        if (pw) {
          pw.value = (pw.value || "") + " ";
          if (pw.element) pw.element.value = pw.value;
        }
      };

      let useInput = useInputWidget ? !!useInputWidget.value : true;
      const uiBtn = document.createElement("button");
      const setUiBtn = () => {
        uiBtn.textContent = useInput ? "📥 输入" : "📝 内容";
        uiBtn.style.background = useInput ? "#0f3460" : "#33333c";
        uiBtn.style.color = useInput ? "#4fc3f7" : "#d8d8de";
      };
      setUiBtn();
      uiBtn.title = "使用上游输入 / 使用本节点内容";
      uiBtn.onclick = () => {
        useInput = !useInput;
        setUiBtn();
        if (useInputWidget) useInputWidget.value = useInput;
      };

      const continueBtn = document.createElement("button");
      continueBtn.textContent = "⏭ 确认输出";
      continueBtn.style.cssText = btnStyle + ";display:none;color:#fff;background:#e94560;font-weight:bold";
      continueBtn.title = "编辑完成后点此输出到下游";

      toolbar.appendChild(modeBtn);
      toolbar.appendChild(pauseBtn);
      toolbar.appendChild(uiBtn);
      toolbar.appendChild(continueBtn);

      const chipInputRow = document.createElement("div");
      chipInputRow.style.cssText = "display:none;gap:4px;align-items:center";
      const chipInput = document.createElement("input");
      chipInput.type = "text";
      chipInput.placeholder = "输入中文翻译 · 英文 tag 直接添加";
      chipInput.style.cssText = "flex:1;background:#141419;border:1px solid #3a3a42;color:#d8d8de;border-radius:5px;padding:2px 6px;outline:none;font:inherit;min-width:0";
      const transBtn = document.createElement("button");
      transBtn.textContent = "🗘 翻译";
      transBtn.style.cssText = btnStyle;
      chipInputRow.appendChild(chipInput);
      chipInputRow.appendChild(transBtn);

      const textarea = document.createElement("textarea");
      textarea.placeholder = "在此输入或编辑 tag,逗号分隔";
      textarea.style.cssText = "width:100%;box-sizing:border-box;background:#141419;border:1px solid #3a3a42;color:#d8d8de;border-radius:5px;padding:4px 6px;outline:none;font:inherit;min-height:60px;resize:vertical";

      const chipArea = document.createElement("div");
      chipArea.style.cssText = "display:flex;flex-wrap:wrap;gap:4px;max-height:140px;overflow-y:auto";
      chipArea.style.display = "none";

      wrap.appendChild(toolbar);
      wrap.appendChild(chipInputRow);
      wrap.appendChild(textarea);
      wrap.appendChild(chipArea);

      const getTags = () => textarea.value.split(/[,，]+/).map((s) => s.trim()).filter(Boolean);
      const cleanOutput = () => getTags().join(", ").replace(/; /g, ", ");
      const syncWidget = () => {
        const clean = cleanOutput();
        textWidget.value = clean;
        if (promptWidget) {
          promptWidget.value = clean;
          if (promptWidget.element) promptWidget.element.value = clean;
        }
      };
      const renderChips = () => {
        chipArea.innerHTML = "";
        getTags().forEach((tag) => {
          const chip = document.createElement("span");
          chip.textContent = tag;
          chip.title = "点击移除";
          chip.style.cssText = "background:#33333c;border:1px solid #3a3a42;border-radius:10px;padding:1px 8px;font-size:11px;cursor:pointer;color:#d8d8de";
          chip.onclick = () => {
            textarea.value = getTags().filter((t) => t !== tag).join(", ");
            syncWidget();
            renderChips();
          };
          chipArea.appendChild(chip);
        });
      };
      const insertTag = (tag) => {
        const tags = getTags();
        if (!tags.includes(tag)) tags.push(tag);
        textarea.value = tags.join(", ");
        syncWidget();
        if (chipMode) renderChips();
      };
      const setChipMode = (on) => {
        textarea.style.display = on ? "none" : "";
        chipInputRow.style.display = on ? "" : "none";
        chipArea.style.display = on ? "flex" : "none";
        modeBtn.textContent = on ? "📋 原文模式" : "⬡ 标签模式";
        if (on) renderChips();
      };
      let chipMode = false;

      modeBtn.onclick = () => setChipMode(!chipMode);
      textarea.addEventListener("input", () => {
        syncWidget();
        if (chipMode) renderChips();
      });
      const doTranslate = async (v) => {
        transBtn.textContent = "⏳ 翻译中...";
        transBtn.disabled = true;
        try {
          const resp = await fetch(`${API_BASE}/tags?q=${encodeURIComponent(v)}`);
          const data = await resp.json();
          if (!data.error && data.tags?.length) {
            data.tags.slice(0, 3).forEach((t) => insertTag(t.tag));
            chipInput.value = "";
          } else {
            chipInput.placeholder = "未找到匹配,请输入英文 tag";
          }
        } catch {
          chipInput.placeholder = "翻译失败,请输入英文 tag";
        }
        transBtn.textContent = "🗘 翻译";
        transBtn.disabled = false;
      };
      chipInput.addEventListener("keydown", (e) => {
        if (e.key !== "Enter") return;
        const v = chipInput.value.trim();
        if (!v) return;
        if (/[一-鿿]/.test(v)) doTranslate(v);
        else { insertTag(v); chipInput.value = ""; }
      });
      transBtn.onclick = () => {
        const v = chipInput.value.trim();
        if (v) doTranslate(v);
      };

      // 暂停模式:执行时后端阻塞,推送 db-pt-show-continue
      const api = window.comfyAPI?.api || app.api;
      const onContinue = (e) => {
        if (e.detail.node_id !== this.id) return;
        if (!useInput) {
          // 内容模式:textarea 保持用户内容;输入模式:同步执行输出
          const uw = this.widgets?.find((w) => w.name === "use_input_text");
          if (uw) textarea.value = uw.value ? (e.detail.text || "") : (textarea.value || "");
        } else {
          textarea.value = e.detail.text || "";
        }
        syncWidget();
        if (chipMode) renderChips();
        if (!pauseMode) {
          // 未开启暂停:立即确认,不阻塞
          fetch(`/danbooru_browser/pt_continue/${this.id}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text: cleanOutput(), gen: e.detail.gen || 0 }),
          }).catch(() => {});
          return;
        }
        continueBtn.style.display = "";
        continueBtn.onclick = async () => {
          try {
            await fetch(`/danbooru_browser/pt_continue/${this.id}`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ text: cleanOutput(), gen: e.detail.gen || 0 }),
            });
            continueBtn.style.display = "none";
          } catch {}
        };
      };
      if (api) {
        if (this._ptHandler) api.removeEventListener("db-pt-show-continue", this._ptHandler);
        this._ptHandler = onContinue;
        api.addEventListener("db-pt-show-continue", this._ptHandler);
      }
      // 节点移除时清理监听,防跨图加载累积
      const onRemoved = nodeType.prototype.onRemoved;
      nodeType.prototype.onRemoved = function () {
        onRemoved?.apply(this, arguments);
        if (api && this._ptHandler) {
          api.removeEventListener("db-pt-show-continue", this._ptHandler);
          this._ptHandler = null;
        }
      };

      this._pt = {
        syncFromWidgets() {
          textarea.value = textWidget.value || "";
          if (useInputWidget) {
            useInput = !!useInputWidget.value;  // 重载后徽标与 widget 一致
            setUiBtn();
          }
          if (chipMode) renderChips();
        },
      };
      textarea.value = textWidget.value || "";
      if (useInputWidget) useInput = !!useInputWidget.value;
      setUiBtn();
      this.addDOMWidget("pt_ui", "div", wrap, { serialize: false, onDraw: () => {} });
      setTimeout(() => this.setSize([Math.max(this.size[0], 300), Math.max(this.size[1], 220)]), 50);
      // widget 在 onNodeCreated 后才创建,延后隐藏内部 text/prompt_text
      setTimeout(() => {
        [textWidget, promptWidget].forEach((w) => {
          if (!w) return;
          w.computeSize = () => [0.1, 20];
          w.serialize = true;
          if (w.element) w.element.style.display = "none";
        });
      }, 300);
    };
  },
});
