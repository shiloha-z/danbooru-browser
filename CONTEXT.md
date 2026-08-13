# Danbooru Browser

A ComfyUI plugin that browses image posts from danbooru, gelbooru, and civitai inside the graph and outputs selected posts — image plus prompt — for further processing.

## 数据源 / Sources

**Site (站点)**:
One of the three connected image sources: danbooru, gelbooru, civitai. They differ in API shape, search capability, and how a prompt is derived.
_Avoid_: platform, 图库

**Post (帖子)**:
A single browsed image together with its metadata — tags, author, original URL, score, rating.
_Avoid_: image (image is the pixel output; post is the data unit the panel deals in)

**Prompt (提示词)**:
The text output paired with a post's image. On danbooru and gelbooru it is the tag list joined into a string; on civitai it is the embedded generation prompt when present, otherwise an empty string.
_Avoid_: tags (tags are the ingredient on boorus; prompt is what the node outputs)

## 输出 / Output

**Output mode (输出模式)**:
One of three behaviours deciding which post the node outputs per execution: manual, auto, list.

- **Manual mode (普通模式)**: outputs the currently selected post; repeated executions re-output the same post.
- **Auto mode (自动模式)**: the cursor advances one post per queue execution, starting from the most recent selection — re-selecting a post restarts the run from there; when the cursor reaches the end of the loaded results, the next page is fetched and appended automatically.
- **List mode (列表模式)**: the cursor advances one post per queue execution over a user-curated list, looping indefinitely; entries may be inserted, removed, or cleared at any time.

**Cursor (游标)**:
The shared advancing position over posts used by auto and list modes; it moves one post forward per queue execution.
_Avoid_: index, pointer, 当前项

**Failed download (下载失败)**:
An image that could not be fetched (404, timeout, blocked site). In auto and list modes the failure is skipped and the cursor continues; the panel marks the failed post.
_Avoid_: error, 报错

## 交互 / Interaction

**Browse panel (浏览面板)**:
The node's custom UI showing the current result set of posts and accepting search, filtering, and selection.

**Filter (筛选)**:
The set of search conditions that narrow the result set: site, tag search, rating, sort order, and per-page count. Tag search exists only on the two boorus; civitai has no tag search.

**Rating (评级)**:
A post's content category. The rating filter is a multi-select over four categories — 普通 (g), 敏感 (s), 可疑 (q), r18 (e) — defaulting to all four selected. The two boorus support all four natively; civitai maps them onto its own nsfw flag.

**Model search (模型搜索)**:
Civitai's replacement for tag search: the search box queries models by name, the user picks a model, and the panel shows that model's images.
_Avoid_: tag search (civitai has none)

## 会话与持久化 / Session & persistence

**Session (会话)**:
The browsing state: search conditions, loaded result pages, cursor, selection, and list. Reopening a saved workflow restores the session — the results are re-fetched automatically.
_Avoid_: state, 浏览记录

**Session reset (会话重置)**:
Changing any filter clears the results, re-fetches from the first page, and returns the cursor to zero.

**Credentials (凭据)**:
API keys for the sites, stored in a local config file. They are never serialized into the workflow JSON, because workflows get shared.
_Avoid_: 密码

**Cache (缓存)**:
Downloaded images kept locally with a bounded size, so repeated selections don't re-download. The panel always displays thumbnails.
