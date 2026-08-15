import { app } from "/scripts/app.js";
import { $el } from "/scripts/ui.js";
import { api } from "/scripts/api.js";

/**
 * 文本(透传)节点面板(移植自 Anima 包,精简版 + 云翻译)。
 *
 * 保留:原文/标签双模式、翻译(chip 中文走本地索引,批量走云翻译)、
 * 暂停模式、使用上游输入切换、文本输入框、⚙️ 设置(翻译提供商)。
 * 裁剪:收藏、预制 tag、提示音、搜索栏、批量选择/合并块/隐藏/权重。
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
            var _tlCache = {};  // 英文 tag → 中文翻译

            // ── 翻译设置状态 ──
            var _transProvider = localStorage.getItem("db_trans_provider") || "free";
            var _transApiKey = localStorage.getItem("db_trans_api_key") || "";
            var _transModel = localStorage.getItem("db_trans_model") || "";
            var _transBaseUrl = localStorage.getItem("db_trans_base_url") || "";
            var _freeMode = localStorage.getItem("db_free_mode") || "baidu";
            var _dsModel = localStorage.getItem("db_ds_model") || "flash";
            var _akInp = null;  // API Key 输入框引用(设置弹窗创建后赋值)
            function _loadTransKey() {
                var p = _transProvider;
                if (p === "deepseek") _transApiKey = localStorage.getItem("db_trans_key_ds") || "";
                else if (p === "custom") _transApiKey = localStorage.getItem("db_trans_key_cu") || "";
                else if (_freeMode === "baidu") _transApiKey = localStorage.getItem("db_trans_key_bd") || "";
                else _transApiKey = "";
                if (_akInp) _akInp.value = _transApiKey;
            }
            function _saveTransKey(k) {
                var p = _transProvider;
                if (p === "deepseek") localStorage.setItem("db_trans_key_ds", k);
                else if (p === "custom") localStorage.setItem("db_trans_key_cu", k);
                else if (_freeMode === "baidu") localStorage.setItem("db_trans_key_bd", k);
                else localStorage.setItem("db_trans_key_ms", k);
                _transApiKey = k;
            }
            _loadTransKey();

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
            // chip 中文翻译:本地中文索引优先,未命中走云翻译
            async function _doChipTranslate(inp) {
                var v = inp.value.trim();
                if (!v) return;
                inp.disabled = true; inp.style.background = "#0d1117";
                chipTransBtn.textContent = "⏳ 翻译中..."; chipTransBtn.style.pointerEvents = "none";
                try {
                    var _r = await fetch("/danbooru_browser/tags?q=" + encodeURIComponent(v));
                    var _d = await _r.json();
                    if (!_d.error && _d.tags && _d.tags.length) {
                        _d.tags.slice(0, 3).forEach(function(t) {
                            _insertTag(t.tag);
                            if (t.cn) _tlCache[t.tag] = t.cn;
                        });
                        inp.value = "";
                    } else {
                        // 本地无匹配 → 云翻译(句子级)
                        var _prov = _transProvider === "free" ? (_freeMode || "baidu") : _transProvider;
                        var _cr = await fetch("/danbooru_anima/cloud_translate", {
                            method: "POST", headers: {"Content-Type":"application/json"},
                            body: JSON.stringify({tags: [v], provider: _prov, api_key: _transApiKey, model: _transModel||"", base_url: _transBaseUrl||"", from_lang: "zh", to_lang: "en", as_sentence: true}),
                        });
                        var _cd = await _cr.json();
                        if (_cd.success && _cd.translations) {
                            var en = _cd.translations[v] || Object.values(_cd.translations)[0] || "";
                            if (en) { en = en.replace(/, /g, "; "); _insertTag(en); _tlCache[en] = v; inp.value = ""; }
                        } else { inp.placeholder = "翻译失败,请输入英文 tag"; }
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

            // ── 🌐 云翻译:批量翻译未翻译标签 ──
            var _cloudBtn = _btn(0, "🌐 翻译", "翻译未翻译标签", null, null, async function(){
                if (!_chipMode) { alert("请先切换到 CHIP 模式（📋）再使用翻译"); return; }
                var _allTags = getTags();
                var _utags = _allTags.filter(function(t){ return !(t in _tlCache) || t.indexOf("; ") >= 0; });
                if (!_utags.length) { alert("所有标签已翻译 ✓"); return; }
                _cloudBtn.textContent = "⏳"; _cloudBtn.style.pointerEvents = "none";
                _loadTransKey(); _transProvider = localStorage.getItem("db_trans_provider") || _transProvider;
                var _prov = _transProvider; var _key = _transApiKey; var _mod = _transModel||""; var _url = _transBaseUrl||"";
                if (_prov === "google") { _prov = "free"; _freeMode = "google"; }
                if (_prov === "free") { var _freeKey = _freeMode === "baidu" ? (localStorage.getItem("db_trans_key_bd")||"") : _key; _prov = _freeMode; _mod = ""; _url = ""; _key = _freeKey; if (_prov === "baidu" && (!_key || _key.indexOf(":") < 0)) { alert("请先在 ⚙️ 设置中填写百度翻译（格式: appid:secret）"); _cloudBtn.textContent = "🌐"; _cloudBtn.style.pointerEvents = ""; return; } }
                else if (_prov === "deepseek") { _prov = "deepseek"; _mod = _dsModel === "pro" ? "deepseek-reasoner" : "deepseek-chat"; _url = "https://api.deepseek.com/v1"; if (!_key) { alert("请先在 ⚙️ 设置中填写 DeepSeek API Key"); _cloudBtn.textContent = "🌐"; _cloudBtn.style.pointerEvents = ""; return; } }
                else if (_prov === "custom") { _url = localStorage.getItem("db_trans_base_url_cu") || ""; _mod = localStorage.getItem("db_trans_model_cu") || ""; if (!_key || !_url) { alert("请先在 ⚙️ 设置中填写自定义 API 信息"); _cloudBtn.textContent = "🌐"; _cloudBtn.style.pointerEvents = ""; return; } }
                else { _prov = "google"; }
                var _apiTags = _utags.map(function(t){
                    if (t.indexOf("; ") >= 0) return t.replace(/; /g, ", ");
                    return (t.indexOf(" ") >= 0 || t.indexOf(",") >= 0) ? t : t.replace(/ /g, "_");
                });
                try {
                    var _tr = await fetch("/danbooru_anima/cloud_translate", {
                        method: "POST", headers: {"Content-Type":"application/json"},
                        body: JSON.stringify({tags: _apiTags, provider: _prov, api_key: _key, model: _mod, base_url: _url}),
                    });
                    var _td = await _tr.json();
                    if (_td.success && _td.translations) {
                        var _cnt = 0;
                        for (var ui = 0; ui < _utags.length; ui++) {
                            if (_td.translations[_apiTags[ui]]) { _tlCache[_utags[ui]] = _td.translations[_apiTags[ui]]; _cnt++; }
                        }
                        renderChips();
                        if (_cnt === 0 && _utags.length > 0) { alert("翻译完成，但未获取到翻译结果。请尝试切换翻译提供商。"); }
                    } else {
                        alert("翻译失败: " + (_td.error || "未知错误"));
                    }
                } catch(e) { alert("请求失败: " + (e.message||e)); }
                _cloudBtn.textContent = "🌐"; _cloudBtn.style.pointerEvents = "";
            });
            toolbar.appendChild(_cloudBtn);

            // ── ⚙️ 设置(翻译提供商) ──
            var _soundPopup = null;
            var _settingsBtn = _btn(0, "⚙️ 设置", "翻译设置", null, null, function(){
                if (_soundPopup) { _soundPopup.remove(); _soundPopup = null; return; }
                var pop = document.createElement('div');
                pop.style.cssText = 'position:fixed;z-index:99999;width:360px;max-height:80vh;overflow-y:auto;background:#1a1a2e;border:1px solid #0f3460;border-radius:8px;box-shadow:0 8px 30px rgba(0,0,0,0.7);padding:16px;';
                pop.appendChild(document.createRange().createContextualFragment('<div style="color:#e0e0e0;font-size:14px;font-weight:bold;margin-bottom:12px;">🌐 翻译设置</div>'));
                var tpDiv = document.createElement('div');
                tpDiv.style.cssText = 'display:flex;align-items:center;gap:8px;margin-bottom:10px;';
                tpDiv.innerHTML = '<span style="color:#888;font-size:12px;white-space:nowrap;">提供商</span>';
                var tpSel = document.createElement('select');
                tpSel.style.cssText = 'flex:1;padding:4px 6px;border:1px solid #0f3460;border-radius:4px;background:#16213e;color:#b0bec5;font-size:12px;cursor:pointer;outline:none;';
                var tProviders = [{v:'free',t:'免费接口'},{v:'deepseek',t:'DeepSeek'},{v:'custom',t:'自定义 API'}];
                for(var pi=0;pi<tProviders.length;pi++){var po=document.createElement('option');po.value=tProviders[pi].v;po.textContent=tProviders[pi].t;if(tProviders[pi].v===_transProvider)po.selected=true;tpSel.appendChild(po);}
                tpSel.onchange = function(){_transProvider=tpSel.value;localStorage.setItem("db_trans_provider",_transProvider);_loadTransKey();_refreshTransUI();};
                tpDiv.appendChild(tpSel); pop.appendChild(tpDiv);
                _freeMode = _freeMode || "baidu";
                var freeDiv = document.createElement('div');
                freeDiv.style.cssText = 'display:flex;align-items:center;gap:8px;margin-bottom:10px;';
                freeDiv.innerHTML = '<span style="color:#888;font-size:11px;white-space:nowrap;">接口</span>';
                var freeSel = document.createElement('select');
                freeSel.style.cssText = 'flex:1;padding:4px 6px;border:1px solid #0f3460;border-radius:4px;background:#16213e;color:#b0bec5;font-size:12px;cursor:pointer;outline:none;';
                freeSel.innerHTML = '<option value="baidu">百度翻译（推荐 · 手机号即开）</option><option value="google">Google 翻译（无需 Key）</option>';
                freeSel.value = _freeMode;
                freeSel.onchange = function(){_freeMode=freeSel.value;localStorage.setItem("db_free_mode",_freeMode);_loadTransKey();_refreshTransUI();};
                freeDiv.appendChild(freeSel); pop.appendChild(freeDiv);
                _dsModel = _dsModel || "flash";
                var dsDiv = document.createElement('div');
                dsDiv.style.cssText = 'display:flex;align-items:center;gap:8px;margin-bottom:10px;';
                dsDiv.innerHTML = '<span style="color:#888;font-size:11px;white-space:nowrap;">模型</span>';
                var dsSel = document.createElement('select');
                dsSel.style.cssText = 'flex:1;padding:4px 6px;border:1px solid #0f3460;border-radius:4px;background:#16213e;color:#b0bec5;font-size:12px;cursor:pointer;outline:none;';
                dsSel.innerHTML = '<option value="flash">V4 Flash</option><option value="pro">V4 Pro</option>';
                dsSel.value = _dsModel;
                dsSel.onchange = function(){_dsModel=dsSel.value;localStorage.setItem("db_ds_model",_dsModel);};
                dsDiv.appendChild(dsSel); pop.appendChild(dsDiv);
                var akDiv = document.createElement('div');
                akDiv.style.cssText = 'display:flex;align-items:center;gap:8px;margin-bottom:10px;';
                akDiv.innerHTML = '<span style="color:#888;font-size:12px;white-space:nowrap;">API Key</span>';
                _akInp = document.createElement('input');
                _akInp.type = 'password'; _akInp.value = _transApiKey; _akInp.placeholder = 'sk-...';
                _akInp.style.cssText = 'flex:1;padding:4px 6px;border:1px solid #0f3460;border-radius:4px;background:#16213e;color:#e0e0e0;font-size:12px;outline:none;';
                _akInp.onchange = function(){_saveTransKey(_akInp.value.trim());};
                akDiv.appendChild(_akInp);
                var eyeBtn = document.createElement('span');
                eyeBtn.textContent = '👁'; eyeBtn.title = '显示/隐藏';
                eyeBtn.style.cssText = 'cursor:pointer;font-size:14px;user-select:none;';
                eyeBtn.onclick = function(){ _akInp.type = _akInp.type === 'password' ? 'text' : 'password'; eyeBtn.textContent = _akInp.type === 'password' ? '👁' : '🙈'; };
                akDiv.appendChild(eyeBtn);
                pop.appendChild(akDiv);
                var hintDiv = document.createElement('div');
                hintDiv.style.cssText = 'margin-bottom:8px;padding:6px 8px;border-radius:4px;background:#0f3460;color:#4fc3f7;font-size:11px;line-height:1.5;display:none;';
                pop.appendChild(hintDiv);
                var mdDiv = document.createElement('div');
                mdDiv.style.cssText = 'display:flex;align-items:center;gap:8px;margin-bottom:10px;';
                mdDiv.innerHTML = '<span style="color:#888;font-size:12px;white-space:nowrap;">Model</span>';
                var mdInp = document.createElement('input');
                mdInp.type = 'text'; mdInp.value = _transModel; mdInp.placeholder = '模型名';
                mdInp.style.cssText = 'flex:1;padding:4px 6px;border:1px solid #0f3460;border-radius:4px;background:#16213e;color:#e0e0e0;font-size:12px;outline:none;';
                mdInp.onchange = function(){_transModel=mdInp.value.trim();localStorage.setItem("db_trans_model",_transModel);};
                mdDiv.appendChild(mdInp); pop.appendChild(mdDiv);
                var buDiv = document.createElement('div');
                buDiv.style.cssText = 'display:flex;align-items:center;gap:8px;margin-bottom:10px;';
                buDiv.innerHTML = '<span style="color:#888;font-size:12px;white-space:nowrap;">Base URL</span>';
                var buInp = document.createElement('input');
                buInp.type = 'text'; buInp.value = _transBaseUrl; buInp.placeholder = 'https://api.xxx.com/v1';
                buInp.style.cssText = 'flex:1;padding:4px 6px;border:1px solid #0f3460;border-radius:4px;background:#16213e;color:#e0e0e0;font-size:12px;outline:none;';
                buInp.onchange = function(){_transBaseUrl=buInp.value.trim();localStorage.setItem("db_trans_base_url",_transBaseUrl);};
                buDiv.appendChild(buInp); pop.appendChild(buDiv);
                var tcDiv = document.createElement('div');
                tcDiv.style.cssText = 'display:flex;gap:8px;margin-bottom:8px;';
                var testTrBtn = document.createElement('span');
                testTrBtn.textContent = '🧪 测试翻译'; testTrBtn.style.cssText = 'padding:4px 10px;border-radius:4px;background:#0f3460;color:#4fc3f7;cursor:pointer;font-size:12px;';
                testTrBtn.onclick = async function(){
                    testTrBtn.textContent = '⏳...'; testTrBtn.style.pointerEvents = 'none';
                    try{
                        var _prov = _transProvider==='free'?_freeMode:_transProvider;
                        var _m = _transProvider==='deepseek'?'deepseek-'+_dsModel:(_transModel||'');
                        var _b = _transBaseUrl||'';
                        var tr = await fetch('/danbooru_anima/cloud_translate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tags:['1girl','red_hair'],provider:_prov,api_key:_transApiKey,model:_m,base_url:_b})});
                        var td = await tr.json();
                        if(td.success){var txt='';for(var k in td.translations)txt+=k+' → '+td.translations[k]+'\n';alert('测试成功:\n'+txt);}
                        else alert('失败: '+(td.error||'未知错误'));
                    }catch(e){alert('请求失败: '+e.message);}
                    testTrBtn.textContent = '🧪 测试翻译'; testTrBtn.style.pointerEvents = '';
                };
                tcDiv.appendChild(testTrBtn);
                var clrCacheBtn = document.createElement('span');
                clrCacheBtn.textContent = '🗑 清除缓存'; clrCacheBtn.style.cssText = 'padding:4px 10px;border-radius:4px;background:#3a1a1a;color:#e94560;cursor:pointer;font-size:12px;';
                clrCacheBtn.onclick = async function(){
                    if(!confirm('确定清除所有云端翻译缓存？'))return;
                    await fetch('/danbooru_anima/clear_translation_cache',{method:'POST'});
                    alert('已清除');
                };
                tcDiv.appendChild(clrCacheBtn);
                pop.appendChild(tcDiv);
                function _refreshTransUI(){
                    var p = _transProvider;
                    freeDiv.style.display = p==='free'?'flex':'none';
                    dsDiv.style.display = p==='deepseek'?'flex':'none';
                    akDiv.style.display = p==='free'&&_freeMode==='google'?'none':'flex';
                    mdDiv.style.display = p==='custom'?'flex':'none';
                    buDiv.style.display = p==='custom'?'flex':'none';
                    if (p === 'free' && _freeMode === 'baidu') {
                        hintDiv.style.display = 'block';
                        hintDiv.innerHTML = '📌 百度翻译申请：<a href="https://fanyi-api.baidu.com" target="_blank" style="color:#ffd93d;">fanyi-api.baidu.com</a> → 开通通用翻译API（免费200万字符/月）→ 获取 APP ID 和密钥<br>👆 API Key 填写格式：<b>appid:密钥</b>（冒号分隔）';
                    } else { hintDiv.style.display = 'none'; }
                }
                _refreshTransUI();
                var okDiv = document.createElement('div');
                okDiv.style.cssText = 'text-align:center;margin-top:12px;';
                var okBtn = document.createElement('span');
                okBtn.textContent = '✓ 确定'; okBtn.style.cssText = 'display:inline-block;padding:5px 20px;border-radius:4px;background:#0f3460;color:#4fc3f7;cursor:pointer;font-size:13px;';
                okBtn.onclick = function(){
                    fetch('/danbooru_anima/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({translation_provider:_transProvider,translation_api_key:_transApiKey,translation_model:_transProvider==='deepseek'?'deepseek-'+_dsModel:(_transModel||''),translation_base_url:_transBaseUrl||''})}).catch(function(){});
                    pop.remove();_soundPopup=null;
                };
                okDiv.appendChild(okBtn); pop.appendChild(okDiv);
                document.body.appendChild(pop);
                pop.style.left = Math.max(10,(window.innerWidth-360)/2)+'px';
                pop.style.top = Math.max(10,(window.innerHeight-500)/2)+'px';
                _soundPopup = pop;
            });
            toolbar.appendChild(_settingsBtn);

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

            // ── 渲染 chip(精简:点击移除;云翻译的中文缓存显示在 chip 上) ──
            function renderChips() {
                chipArea.innerHTML = "";
                var tags = getTags();
                if (!tags.length) { chipArea.innerHTML = '<span style="color:#555;font-size:12px;">无标签</span>'; return; }
                for(var i=0;i<tags.length;i++){(function(ii){
                    var tag=tags[ii],cn=_tlCache[tag]||"";
                    var col=_tagColor(tag);
                    var label=cn?tag+"（"+cn+"）":tag;
                    var chip=$el("div",{textContent:label,title:cn?"点击移除":"点击移除",style:{display:"inline-flex",alignItems:"center",padding:"2px 8px",borderRadius:"4px",fontSize:"11px",background:col+"88",color:"#fff",border:"1px solid "+col,cursor:"pointer",userSelect:"none",maxWidth:"300px",overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}});
                    chip.onclick=function(){var t2=getTags().filter(function(t){return t!==tag;});setTags(t2);};
                    chipArea.appendChild(chip);
                })(i);}
            }
            function _insertTag(tag) {
                var tags = getTags();
                if (tags.indexOf(tag) < 0) tags.push(tag);
                tagTextarea.value = tags.join(", ");
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
