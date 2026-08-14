import { app } from "/scripts/app.js";
import { $el } from "/scripts/ui.js";
import { api } from "/scripts/api.js";

/**
 * 文本(透传)节点面板(移植自 Anima 包,精简版)。
 *
 * 保留:原文/标签双模式、chip 翻译(本地中文索引)、暂停模式、
 * 使用上游输入切换、文本输入框。
 * 裁剪:收藏、预制 tag、云翻译、设置弹窗、提示音、搜索栏、
 * 批量选择/合并块/隐藏/权重、参考包后端配色(内置规则保留)。
 */

app.registerExtension({
    name: "DanbooruBrowser.TextPassthrough",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "DanbooruBrowserTextPassthrough") return;
        const onCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            onCreated?.apply(this, arguments);
            const node = this;

            const textWidget = node.widgets?.find(w => w.name === "text");
            if (textWidget) { textWidget.computeSize = () => [0.1, 20]; textWidget.serialize = true; }
            setTimeout(() => { const w = node.widgets?.find(x => x.name === "text"); if (w && w.element) w.element.style.display = "none"; }, 50);

            var _pauseMode = localStorage.getItem("db_pt_pause_" + node.id) === "true", _useInput = true;
            var _chipMode = localStorage.getItem("db_pt_chip_mode") === "1";

            const container = $el("div", { style: { width: "100%", height: "100%", position: "relative", display: "flex", flexDirection: "column", background: "#1a1a2e", borderRadius: "4px", overflow: "hidden" } });

            // ── 工具栏 ──
            const toolbar = $el("div", { style: { display: "flex", gap: "6px", padding: "3px 6px", borderBottom: "1px solid #0f3460", background: "#0d1b2a", flexShrink: 0, flexWrap: "wrap", alignItems: "center" } });
            const chipArea = $el("div", { style: { flex: 1, padding: "6px 8px", overflowY: "auto", display: "flex", flexWrap: "wrap", gap: "4px", alignContent: "flex-start" } });
            chipArea.style.display = "none";
            const chipInput = $el("textarea", { placeholder: "🌐 输入中文翻译 · 英文tag直接添加", style: { display: "none", width: "100%", padding: "4px 8px", border: "1px solid #0f3460", background: "#16213e", color: "#e0e0e0", fontSize: "12px", outline: "none", boxSizing: "border-box", flexShrink: 0, resize: "vertical", minHeight: "36px", lineHeight: "1.4", fontFamily: "inherit" } });
            const chipInputRow = $el("div", { style: { display: "none", gap: "4px", flexShrink: 0 } });
            chipInputRow.appendChild(chipInput);
            var chipTransBtn = $el("span", { textContent: "🗘 翻译", title: "翻译中文并加入节点", style: { display: "none", padding: "4px 10px", border: "1px solid #0f3460", borderRadius: "3px", cursor: "pointer", fontSize: "11px", background: "#0f3460", color: "#4fc3f7", whiteSpace: "nowrap", userSelect: "none", alignSelf: "flex-start" } });
            chipTransBtn.onclick = function() { _doChipTranslate(chipInput); };
            chipInputRow.appendChild(chipTransBtn);
            chipInput.onkeydown = function(ev) {
                if (ev.key === "Enter") {
                    ev.preventDefault();
                    var v = chipInput.value.trim();
                    if (!v) return;
                    if (/[一-鿿]/.test(v)) { _doChipTranslate(chipInput); }
                    else { _insertTag(v); chipInput.value = ""; }
                }
            };
            // 中文翻译:本地中文索引(本项目 /tags 路由),取前 3 个候选加入
            async function _doChipTranslate(inp) {
                var v = inp.value.trim();
                if (!v) return;
                inp.disabled = true; inp.style.background = "#0d1117";
                chipTransBtn.textContent = "⏳ 翻译中..."; chipTransBtn.style.pointerEvents = "none";
                try {
                    var _r = await fetch("/danbooru_browser/tags?q=" + encodeURIComponent(v));
                    var _d = await _r.json();
                    if (!_d.error && _d.tags && _d.tags.length) {
                        _d.tags.slice(0, 3).forEach(function(t) { _insertTag(t.tag); });
                        inp.value = "";
                    } else {
                        inp.placeholder = "未找到匹配,请输入英文 tag";
                    }
                } catch(e) { inp.placeholder = "翻译失败,请输入英文 tag"; }
                inp.disabled = false; inp.style.background = "";
                chipTransBtn.textContent = "🗘 翻译"; chipTransBtn.style.pointerEvents = "";
            }
            const tagTextarea = $el("textarea", { placeholder: "在此输入或编辑 tag，逗号分隔", style: { flex: 1, width: "100%", padding: "6px 8px", border: "1px solid #0f3460", background: "#16213e", color: "#e0e0e0", fontSize: "13px", outline: "none", resize: "none", boxSizing: "border-box", fontFamily: "inherit", lineHeight: "1.5" } });

            chipInputRow.style.display = _chipMode ? "flex" : "none";
            chipTransBtn.style.display = _chipMode ? "inline" : "none";

            // 内置配色规则(无后端依赖)
            function _tagColor(tag) {
                var _r = "#555555";
                if (!tag) return _r;
                if (tag.startsWith("@")) return "#e91e63";
                if (/^score_|^rating_|^year_/.test(tag)) _r = "#ff9800";
                else if (/^\d+(?:girl|boy|other|1other)$/.test(tag)) _r = "#00bcd4";
                else if (/^1(shot|girl|boy|other|head|breast|animal|pov|night|day)$/.test(tag)) _r = "#00bcd4";
                return _r;
            }
            // ── 隐藏内部 widget ──
            setTimeout(function() {
                ["use_input_text", "prompt_text", "text"].forEach(function(n) {
                    var w = node.widgets?.find(function(x){return x.name===n;});
                    if (!w) return;
                    w.computeSize = function(){return [0.1, 20];};
                    w.serialize = true;
                    if (w.element) w.element.style.display = "none";
                });
            }, 300);

            function _btn(x, txt, title, bg, fc, fn) {
                var b = $el("span", { textContent: txt, title: title, style: { fontSize: "11px", cursor: "pointer", background: bg || "rgba(255,255,255,0.06)", color: fc || "#ccc", padding: "3px 8px", borderRadius: "3px", whiteSpace: "nowrap", userSelect: "none" }, onclick: fn });
                return b;
            }
            var _chipModeBtn = _btn(0, _chipMode ? "⬡ 标签模式" : "📋 原文模式", "点击切换 原文 ↔ CHIP 芯片模式", "#0f3460", "#4fc3f7", function(){_chipMode=!_chipMode;localStorage.setItem("db_pt_chip_mode",_chipMode?"1":"0");chipArea.style.display=_chipMode?"flex":"none";chipInputRow.style.display=_chipMode?"flex":"none";chipTransBtn.style.display=_chipMode?"inline":"none";tagTextarea.style.display=_chipMode?"none":"flex";_chipModeBtn.textContent=_chipMode?"⬡ 标签模式":"📋 原文模式";if(_chipMode)renderChips();}); _chipModeBtn.style.fontSize = "12px"; _chipModeBtn.style.fontWeight = "bold"; _chipModeBtn.style.padding = "4px 10px"; toolbar.appendChild(_chipModeBtn);

            var pauseBtn = _btn(0, _pauseMode?"⏸ 暂停 开":"⏸ 暂停 关", "点击开启暂停模式", _pauseMode?"#0f3460":null, _pauseMode?"#4fc3f7":null, function(){_pauseMode=!_pauseMode;pauseBtn.textContent=_pauseMode?"⏸ 暂停 开":"⏸ 暂停 关";pauseBtn.style.background=_pauseMode?"#0f3460":"rgba(255,255,255,0.06)";localStorage.setItem("db_pt_pause_"+node.id,_pauseMode);var _pw3=node.widgets?.find(function(w){return w.name==="prompt_text";});if(_pw3){_pw3.value=_pw3.value+" "; if(_pw3.element)_pw3.element.value=_pw3.value;}});
            var uiBtn = _btn(0, "📥 输入", "使用上游输入", "#0f3460", "#4fc3f7", function(){_useInput=!_useInput;uiBtn.textContent=_useInput?"📥 输入":"📝 内容";uiBtn.style.background=_useInput?"#0f3460":"rgba(255,255,255,0.06)";var uw=node.widgets?.find(function(w){return w.name==="use_input_text";});if(uw)uw.value=_useInput;});
            var continueBtn = _btn(0, "⏭ 确认输出", "编辑完成后点此输出到下游", "#e94560", "#fff", function(){}); continueBtn.style.display = "none"; continueBtn.style.fontSize = "13px"; continueBtn.style.fontWeight = "bold"; continueBtn.style.boxShadow = "0 0 8px rgba(233,69,96,0.4)";
            toolbar.appendChild(pauseBtn);
            toolbar.appendChild(uiBtn);
            toolbar.appendChild(continueBtn);

            function getTags() { return tagTextarea.value.split(/[,，]+/).map(function(s){return s.trim();}).filter(Boolean); }
            function setTags(tags) { tagTextarea.value = tags.join(", "); syncWidget(); if(_chipMode) renderChips(); }
            function syncWidget() {
                var _clean = getTags().join(", ").replace(/; /g, ", ");
                var _tw2 = node.widgets?.find(function(w){return w.name==="text";});
                if(_tw2) _tw2.value = _clean;
                var pw = node.widgets?.find(function(w){return w.name==="prompt_text";});
                if(pw) { pw.value = _clean; if(pw.element) pw.element.value = _clean; }
            }
            function _getCleanOutput() {
                return getTags().join(", ").replace(/; /g, ", ");
            }

            // ── 渲染 chip(精简:点击移除) ──
            function renderChips() {
                chipArea.innerHTML = "";
                var tags = getTags();
                if (!tags.length) { chipArea.innerHTML = '<span style="color:#555;font-size:12px;">无标签</span>'; return; }
                for(var i=0;i<tags.length;i++){(function(ii){
                    var tag=tags[ii];
                    var col=_tagColor(tag);
                    var chip=$el("div",{textContent:tag,title:"点击移除",style:{display:"inline-flex",alignItems:"center",padding:"2px 8px",borderRadius:"4px",fontSize:"11px",background:col+"88",color:"#fff",border:"1px solid "+col,cursor:"pointer",userSelect:"none",maxWidth:"300px",overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}});
                    chip.onclick=function(){var t2=getTags().filter(function(t){return t!==tag;});setTags(t2);};
                    chipArea.appendChild(chip);
                })(i);}
            }
            function _insertTag(tag) {
                var ta = tagTextarea;
                var tags = getTags();
                if (tags.indexOf(tag) < 0) tags.push(tag);
                ta.value = tags.join(", ");
                syncWidget();
                if(_chipMode) renderChips();
            }
            tagTextarea.oninput = function(){syncWidget();};

            container.append(toolbar, chipArea, chipInputRow, tagTextarea);

            // ── 暂停逻辑 ──
            if (node._ptHandler) api.removeEventListener("db-pt-show-continue", node._ptHandler);
            node._ptHandler = function(e) {
                if (e.detail.node_id != node.id) return;
                if (!_useInput) {
                    var uw = node.widgets?.find(function(w){return w.name==="use_input_text";});
                    if (uw) tagTextarea.value = uw.value ? (e.detail.text || "") : (tagTextarea.value || "");
                } else {
                    tagTextarea.value = e.detail.text || "";
                }
                syncWidget();
                if(_chipMode) renderChips();
                if (!_pauseMode) {
                    fetch("/danbooru_browser/pt_continue/" + node.id, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({ text: _getCleanOutput(), gen: e.detail.gen || 0 }) }).catch(function(){});
                    return;
                }
                continueBtn.style.display = "inline";
                continueBtn.onclick = async function() {
                    try {
                        await fetch("/danbooru_browser/pt_continue/" + node.id, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: _getCleanOutput(), gen: e.detail.gen || 0 }) });
                        continueBtn.style.display = "none";
                    } catch(e){}
                };
            };
            api.addEventListener("db-pt-show-continue", node._ptHandler);

            // 保存到 localStorage(键含 node.id,防跨工作流串数据)
            setInterval(function() {
                try {
                    if (tagTextarea.value) {
                        localStorage.setItem("db_pt_content_" + node.id, tagTextarea.value);
                        syncWidget();
                    }
                } catch(e){}
            }, 3000);
            // 初始化恢复
            setTimeout(function() {
                var _pw = node.widgets?.find(w => w.name === "prompt_text");
                var _uiw2 = node.widgets?.find(w => w.name === "use_input_text");
                var _v = _pw ? _pw.value : "";
                if (_v) {
                    tagTextarea.value = _v;
                } else {
                    _v = localStorage.getItem("db_pt_content_" + node.id) || "";
                    if (_v) tagTextarea.value = _v;
                }
                if (_uiw2) {
                    _useInput = _uiw2.value;
                    uiBtn.textContent = _useInput ? "📥 输入" : "📝 内容";
                    uiBtn.style.background = _useInput ? "#0f3460" : "rgba(0,0,0,0.5)";
                }
                syncWidget();
                if (_chipMode) { chipArea.style.display = "flex"; chipInput.style.display = "block"; tagTextarea.style.display = "none"; renderChips(); }
            }, 500);
            node.serialize_widgets = true;
            this.addDOMWidget("db_pt_ui","div",container,{onDraw:function(){}});
            container.style.pointerEvents = "auto";
            container.style.position = "relative";
            if (node.size) node.setSize([node.size[0]*2, node.size[1]*3]);
        };
    },
});
