import { app } from "../../scripts/app.js";

/**
 * 文本(透传)节点面板(移植自 Anima 包,核心版,issue #24)。
 *
 * 原文模式:textarea 逗号分隔编辑;标签模式:chip 展示,点击移除,输入框回车添加。
 * 裁剪:中文翻译/收藏/云、执行中暂停编辑、PNG 元数据写回。
 */

app.registerExtension({
  name: "DanbooruBrowser.TextPassthrough",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== "DanbooruBrowserTextPassthrough") return;
    // 工作流恢复:widget 值在 configure 时应用,此时把已加载内容同步进 textarea
    const onConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
      onConfigure?.apply(this, arguments);
      const textWidget = this.widgets?.find((w) => w.name === "text");
      if (textWidget && this._ptTextarea) this._ptTextarea.value = textWidget.value || "";
    };
    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      onNodeCreated?.apply(this, arguments);

      const textWidget = this.widgets?.find((w) => w.name === "text");
      const promptWidget = this.widgets?.find((w) => w.name === "prompt_text");
      if (!textWidget) return;

      const wrap = document.createElement("div");
      wrap.style.cssText = "display:flex;flex-direction:column;gap:4px;padding:6px;min-width:220px";

      const toolbar = document.createElement("div");
      toolbar.style.cssText = "display:flex;gap:4px;align-items:center";
      const modeBtn = document.createElement("button");
      modeBtn.textContent = "⬡ 标签模式";
      modeBtn.title = "切换 原文 ↔ 标签(chip)模式";
      modeBtn.style.cssText = "background:#33333c;border:1px solid #3a3a42;color:#d8d8de;border-radius:5px;padding:2px 8px;cursor:pointer;font:inherit";
      const addInput = document.createElement("input");
      addInput.type = "text";
      addInput.placeholder = "输入 tag 回车添加";
      addInput.style.cssText = "flex:1;background:#141419;border:1px solid #3a3a42;color:#d8d8de;border-radius:5px;padding:2px 6px;outline:none;font:inherit;min-width:0";
      addInput.style.display = "none";
      toolbar.appendChild(modeBtn);
      toolbar.appendChild(addInput);

      const textarea = document.createElement("textarea");
      textarea.placeholder = "在此输入或编辑 tag,逗号分隔";
      textarea.style.cssText = "width:100%;box-sizing:border-box;background:#141419;border:1px solid #3a3a42;color:#d8d8de;border-radius:5px;padding:4px 6px;outline:none;font:inherit;min-height:60px;resize:vertical";

      const chipArea = document.createElement("div");
      chipArea.style.cssText = "display:flex;flex-wrap:wrap;gap:4px;max-height:140px;overflow-y:auto";
      chipArea.style.display = "none";

      wrap.appendChild(toolbar);
      wrap.appendChild(textarea);
      wrap.appendChild(chipArea);

      const getTags = () => textarea.value.split(/[,，]+/).map((s) => s.trim()).filter(Boolean);
      const syncWidget = () => { textWidget.value = textarea.value; };
      const renderChips = () => {
        chipArea.innerHTML = "";
        getTags().forEach((tag) => {
          const chip = document.createElement("span");
          chip.textContent = tag;
          chip.title = "点击移除";
          chip.style.cssText = "background:#33333c;border:1px solid #3a3a42;border-radius:10px;padding:1px 8px;font-size:11px;cursor:pointer;color:#d8d8de";
          chip.onclick = () => {
            const tags = getTags().filter((t) => t !== tag);
            textarea.value = tags.join(", ");
            syncWidget();
            renderChips();
          };
          chipArea.appendChild(chip);
        });
      };
      const setChipMode = (on) => {
        textarea.style.display = on ? "none" : "";
        addInput.style.display = on ? "" : "none";
        chipArea.style.display = on ? "flex" : "none";
        modeBtn.textContent = on ? "📋 原文模式" : "⬡ 标签模式";
        if (on) renderChips();
      };
      let chipMode = false;

      modeBtn.onclick = () => setChipMode(!chipMode);
      addInput.addEventListener("keydown", (e) => {
        if (e.key !== "Enter") return;
        const tag = addInput.value.trim();
        if (!tag) return;
        const tags = getTags();
        if (!tags.includes(tag)) tags.push(tag);
        textarea.value = tags.join(", ");
        addInput.value = "";
        syncWidget();
        renderChips();
      });
      textarea.addEventListener("input", () => {
        syncWidget();
        if (chipMode) renderChips();
      });

      textarea.value = textWidget.value || "";
      this._ptTextarea = textarea;  // onConfigure 同步用(工作流恢复)
      this.addDOMWidget("pt_ui", "div", wrap, { serialize: false });
      setTimeout(() => this.setSize([Math.max(this.size[0], 260), Math.max(this.size[1], 180)]), 50);
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
