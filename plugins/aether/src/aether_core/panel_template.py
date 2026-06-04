from __future__ import annotations


PANEL_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Aether Memory Panel</title>
  <style>
    :root {
      --paper: #f5f1e8;
      --ink: #18211f;
      --muted: #68736f;
      --line: #d5cdbd;
      --panel: #fffdf7;
      --panel-soft: #ece4d5;
      --teal: #2c817a;
      --red: #aa4937;
      --blue: #4c6f9b;
      --gold: #9a6b13;
      --shadow: 0 16px 42px rgba(41, 35, 23, .12);
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--paper);
      color: var(--ink);
      font-family: ui-serif, Georgia, Cambria, "Times New Roman", serif;
    }
    button, input, select { font: inherit; }
    button, a { -webkit-tap-highlight-color: transparent; }
    .shell {
      display: grid;
      grid-template-columns: 280px minmax(0, 1fr);
      min-height: 100vh;
    }
    aside {
      border-right: 1px solid var(--line);
      padding: 22px;
      background: #eee6d8;
      position: sticky;
      top: 0;
      height: 100vh;
      overflow: auto;
    }
    main {
      padding: 24px;
      min-width: 0;
    }
    h1, h2, h3, h4 {
      margin: 0;
      letter-spacing: 0;
      line-height: 1.1;
    }
    h1 { font-size: 30px; }
    h2 { font-size: 24px; }
    h3 { font-size: 18px; overflow-wrap: anywhere; }
    h4 { font-size: 13px; color: var(--muted); text-transform: uppercase; }
    p {
      margin: 0;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.45;
      overflow-wrap: anywhere;
    }
    .sub {
      margin: 4px 0 20px;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.45;
    }
    .stats {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
      margin: 18px 0;
    }
    .stat {
      border: 1px solid var(--line);
      background: rgba(255,255,255,.45);
      padding: 10px;
      border-radius: 8px;
    }
    .stat b {
      display: block;
      font-size: 22px;
      line-height: 1;
    }
    .stat span {
      color: var(--muted);
      font-size: 12px;
    }
    .tabs {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 8px;
      margin-top: 16px;
    }
    .tab, .back, .download, .close {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: transparent;
      color: var(--ink);
      cursor: pointer;
      min-height: 38px;
      text-decoration: none;
    }
    .tab {
      padding: 9px 6px;
    }
    .tab.active {
      background: var(--ink);
      color: var(--paper);
      border-color: var(--ink);
    }
    .controls {
      display: grid;
      gap: 10px;
      margin-top: 18px;
    }
    .controls label {
      display: grid;
      gap: 5px;
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0;
    }
    input, select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 9px 10px;
      background: var(--panel);
      color: var(--ink);
      min-height: 39px;
    }
    .topline {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: center;
      margin-bottom: 16px;
    }
    .count {
      color: var(--muted);
      font-size: 14px;
      white-space: nowrap;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(286px, 1fr));
      gap: 16px;
      align-items: stretch;
    }
    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      overflow: hidden;
      display: grid;
      grid-template-rows: 150px auto;
      min-width: 0;
      text-align: left;
      cursor: pointer;
      padding: 0;
    }
    .card:hover {
      border-color: #a99b84;
      transform: translateY(-1px);
    }
    .thumbs {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 1px;
      background: var(--line);
      min-height: 150px;
    }
    .thumbs img {
      width: 100%;
      height: 150px;
      object-fit: cover;
      background: #ddd4c5;
      display: block;
    }
    .thumbs .empty, .empty-gallery {
      display: grid;
      place-items: center;
      color: var(--muted);
      background: #ebe3d3;
      min-height: 150px;
      font-size: 13px;
    }
    .thumbs .empty { grid-column: 1 / -1; }
    .body {
      padding: 14px;
      min-width: 0;
    }
    .card-head {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: flex-start;
    }
    .meta, .chips {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .meta { margin-bottom: 10px; }
    .pill {
      border-radius: 999px;
      padding: 4px 8px;
      border: 1px solid var(--line);
      color: var(--muted);
      font-size: 12px;
      line-height: 1;
      max-width: 100%;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .pill.type { color: var(--teal); border-color: rgba(44, 129, 122, .35); }
    .pill.recipe { color: var(--red); border-color: rgba(170, 73, 55, .35); }
    .pill.system { color: var(--blue); border-color: rgba(76, 111, 155, .35); }
    .pill.generated { color: var(--gold); border-color: rgba(154, 107, 19, .36); }
    .favorite-button {
      border: 1px solid var(--line);
      border-radius: 999px;
      background: #f6efe1;
      color: var(--muted);
      cursor: pointer;
      flex: 0 0 auto;
      font-size: 15px;
      line-height: 1;
      min-height: 28px;
      min-width: 32px;
      padding: 5px 8px;
    }
    .favorite-button.active {
      border-color: rgba(154, 107, 19, .55);
      color: var(--gold);
      background: #fff5d8;
    }
    .relations {
      margin-top: 12px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
      max-height: 54px;
      overflow: hidden;
    }
    .detail {
      display: grid;
      gap: 18px;
    }
    .detail-head {
      display: grid;
      gap: 12px;
      max-width: 980px;
    }
    .detail-title {
      display: flex;
      justify-content: space-between;
      gap: 14px;
      align-items: flex-start;
    }
    .back {
      padding: 8px 12px;
      background: var(--panel);
      flex: 0 0 auto;
    }
    .detail-top {
      display: grid;
      grid-template-columns: minmax(0, 1.1fr) minmax(300px, .9fr);
      gap: 18px;
      align-items: start;
    }
    .detail-media {
      display: grid;
      gap: 16px;
      min-width: 0;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      min-width: 0;
    }
    .section {
      display: grid;
      gap: 10px;
      min-width: 0;
    }
    .section + .section {
      margin-top: 16px;
      padding-top: 14px;
      border-top: 1px solid var(--line);
    }
    .list {
      display: grid;
      gap: 8px;
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .list li, .relation-row {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(255,255,255,.42);
      padding: 10px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.4;
      overflow-wrap: anywhere;
    }
    .list b {
      display: block;
      color: var(--ink);
      font-size: 14px;
      margin-bottom: 4px;
    }
    .nested-list {
      margin: 8px 0 0;
      padding-left: 18px;
    }
    .nested-list li {
      border: 0;
      border-radius: 0;
      background: transparent;
      padding: 2px 0;
      list-style: disc;
    }
    .relation-row b {
      display: block;
      color: var(--ink);
      font-size: 14px;
      margin-bottom: 3px;
    }
    .gallery {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(158px, 1fr));
      gap: 10px;
    }
    .image-tile {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      min-width: 0;
    }
    .preview {
      display: block;
      width: 100%;
      border: 0;
      padding: 0;
      background: #ddd4c5;
      cursor: zoom-in;
    }
    .preview img {
      display: block;
      width: 100%;
      aspect-ratio: 1;
      object-fit: cover;
    }
    .image-actions {
      display: flex;
      justify-content: space-between;
      gap: 8px;
      align-items: center;
      padding: 8px;
    }
    .image-actions span {
      color: var(--muted);
      font-size: 12px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .download {
      min-height: 0;
      padding: 5px 8px;
      color: var(--ink);
      font-size: 12px;
      background: #f4eee1;
      flex: 0 0 auto;
    }
    .error {
      padding: 18px;
      background: #fff3ed;
      border: 1px solid #e2b3a2;
      border-radius: 8px;
      color: #7a2a1c;
    }
    .lightbox {
      position: fixed;
      inset: 0;
      display: none;
      place-items: center;
      padding: 24px;
      background: rgba(17, 22, 21, .82);
      z-index: 10;
    }
    .lightbox.active { display: grid; }
    .lightbox-inner {
      display: grid;
      gap: 10px;
      max-width: min(1100px, 96vw);
      max-height: 94vh;
    }
    .lightbox img {
      max-width: 100%;
      max-height: 82vh;
      object-fit: contain;
      background: #111;
      border-radius: 8px;
    }
    .lightbox-bar {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: center;
      color: var(--paper);
    }
    .close {
      padding: 8px 12px;
      color: var(--paper);
      border-color: rgba(255,255,255,.35);
    }
    @media (max-width: 900px) {
      .shell { grid-template-columns: 1fr; }
      aside {
        position: relative;
        height: auto;
        border-right: 0;
        border-bottom: 1px solid var(--line);
      }
      main { padding: 16px; }
      .detail-top { grid-template-columns: 1fr; }
      .tabs { grid-template-columns: repeat(4, 1fr); }
    }
  </style>
</head>
<body>
  <div class="shell">
    <aside>
      <h1>Aether</h1>
      <p class="sub">Local visual memory panel</p>
      <div class="stats" id="stats"></div>
      <div class="tabs">
        <button class="tab" data-view="favorites">Favorites</button>
        <button class="tab active" data-view="recipes">Recipes</button>
        <button class="tab" data-view="visual_systems">Systems</button>
        <button class="tab" data-view="visual_assets">Assets</button>
      </div>
      <div class="controls">
        <label>Search <input id="search" placeholder="name, summary, tag"></label>
        <label>Type <select id="type"></select></label>
        <label>Status <select id="status"></select></label>
      </div>
    </aside>
    <main>
      <div id="content"></div>
    </main>
  </div>
  <div class="lightbox" id="lightbox" aria-hidden="true"></div>
  <script>
    const state = { data: null, view: "recipes", q: "", type: "", status: "active", detail: null };
    const labels = { favorites: "Favorites", recipes: "Recipes", visual_systems: "Systems", visual_assets: "Assets" };
    const badgeClasses = { favorites: "generated", recipes: "recipe", visual_systems: "system", visual_assets: "type" };

    function esc(value) {
      return String(value ?? "").replace(/[&<>"']/g, char => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
      }[char]));
    }

    function attr(value) {
      return esc(value).replace(/`/g, "&#96;");
    }

    function existingImages(images) {
      return (images || []).filter(image => image.exists !== false);
    }

    function imageSet(item) {
      return [...existingImages(item.reference_images), ...existingImages(item.generated_images)];
    }

    function searchableText(item) {
      return [
        item.name, item.summary, item.definition, item.type, item.kind, item.status,
        ...(item.tags || []), ...(item.required_asset_types || []), ...(item.use_cases || [])
      ].join(" ").toLowerCase();
    }

    function matches(item) {
      const q = state.q.trim().toLowerCase();
      if (q && !searchableText(item).includes(q)) return false;
      if (state.status && item.status !== state.status) return false;
      if (state.type && item.type !== state.type && item.kind !== state.type && !(item.required_asset_types || []).includes(state.type)) return false;
      return true;
    }

    function renderStats() {
      const s = state.data.summary;
      document.getElementById("stats").innerHTML = [
        ["Assets", s.visual_asset_count],
        ["Recipes", s.recipe_count],
        ["Systems", s.visual_system_count],
        ["Favorites", s.favorite_count],
        ["Generated", s.generated_file_count]
      ].map(([label, value]) => `<div class="stat"><b>${value}</b><span>${label}</span></div>`).join("");
    }

    function renderFilters() {
      const typeValues = new Set();
      const statusValues = new Set();
      for (const item of state.data.visual_assets) {
        if (item.type) typeValues.add(item.type);
        if (item.status) statusValues.add(item.status);
      }
      for (const item of [...state.data.recipes, ...state.data.visual_systems]) {
        if (item.kind) typeValues.add(item.kind);
        if (item.status) statusValues.add(item.status);
        for (const type of item.required_asset_types || []) typeValues.add(type);
      }
      const type = document.getElementById("type");
      const status = document.getElementById("status");
      type.innerHTML = `<option value="">All</option>` + [...typeValues].sort().map(v => `<option>${esc(v)}</option>`).join("");
      status.innerHTML = `<option value="">All</option>` + [...statusValues].sort().map(v => `<option>${esc(v)}</option>`).join("");
      type.value = state.type;
      status.value = state.status;
    }

    function chips(values, className = "") {
      return (values || []).filter(Boolean).map(value => `<span class="pill ${className}">${esc(value)}</span>`).join("");
    }

    function imageThumbs(item) {
      const images = imageSet(item).slice(0, 3);
      return images.length
        ? images.map(image => `<img src="${attr(image.src)}" alt="${attr(image.label)}" loading="lazy">`).join("")
        : `<div class="empty">No linked image</div>`;
    }

    function card(item) {
      const type = item.type || item.kind || (item.required_asset_types || []).slice(0, 2).join(", ") || "record";
      const relation = item.related_assets && item.related_assets.length
        ? item.related_assets.slice(0, 4).map(asset => `${esc(asset.role)}: ${esc(asset.name)}`).join(" | ")
        : "";
      const imageCounts = `${existingImages(item.reference_images).length} ref / ${existingImages(item.generated_images).length} gen`;
      const view = sourceView(item);
      return `<article class="card" tabindex="0" data-id="${attr(item.id)}" data-source-view="${attr(view)}">
        <div class="thumbs">${imageThumbs(item)}</div>
        <div class="body">
          <div class="card-head">
            <div class="meta">
              <span class="pill ${badgeClasses[view] || "type"}">${esc(type)}</span>
              ${item.status ? `<span class="pill">${esc(item.status)}</span>` : ""}
              <span class="pill">${esc(imageCounts)}</span>
            </div>
            ${favoriteButton(item)}
          </div>
          <h3>${esc(item.name)}</h3>
          <p>${esc(item.summary || item.definition || "")}</p>
          ${relation ? `<div class="relations">${relation}</div>` : ""}
        </div>
      </article>`;
    }

    function imageGallery(images, emptyText) {
      images = existingImages(images);
      if (!images || !images.length) return `<div class="empty-gallery">${esc(emptyText)}</div>`;
      return `<div class="gallery">${images.map(image => `<div class="image-tile">
        <button class="preview" data-src="${attr(image.src)}" data-label="${attr(image.label)}">
          <img src="${attr(image.src)}" alt="${attr(image.label)}" loading="lazy">
        </button>
        <div class="image-actions">
          <span>${esc(image.label)}</span>
          <a class="download" href="${attr(image.src)}" download="${attr(image.label)}">Download</a>
        </div>
      </div>`).join("")}</div>`;
    }

    function titleCaseKey(value) {
      return String(value ?? "").replace(/[_-]+/g, " ").replace(/\b\w/g, char => char.toUpperCase());
    }

    function valueLines(value) {
      if (Array.isArray(value)) return value.flatMap(valueLines);
      if (value && typeof value === "object") return [JSON.stringify(value, null, 2)];
      return value === undefined || value === null || value === "" ? [] : [String(value)];
    }

    function ruleItem(item) {
      if (!item || typeof item !== "object" || Array.isArray(item)) {
        return `<li>${esc(item)}</li>`;
      }
      const title = titleCaseKey(item.key || item.name || item.type || "Rule");
      const reason = item.reason ? `<p>${esc(item.reason)}</p>` : "";
      const values = valueLines(item.value ?? item.values ?? item.rule ?? item.rules);
      const valueHtml = values.length
        ? `<ul class="nested-list">${values.map(value => `<li>${esc(value)}</li>`).join("")}</ul>`
        : "";
      const fallback = !reason && !valueHtml ? `<p>${esc(JSON.stringify(item, null, 2))}</p>` : "";
      return `<li><b>${esc(title)}</b>${reason}${valueHtml}${fallback}</li>`;
    }

    function listBlock(title, values) {
      const items = (values || []).filter(Boolean);
      if (!items.length) return "";
      return `<div class="section"><h4>${esc(title)}</h4><ul class="list">${items.map(ruleItem).join("")}</ul></div>`;
    }

    function relationBlock(item) {
      const systems = (item.parent_systems || []).map(system => `<div class="relation-row">
        <b>${esc(system.name)}</b>${esc(system.kind || "visual system")} ${system.status ? `- ${esc(system.status)}` : ""}
      </div>`).join("");
      const assets = (item.related_assets || []).map(asset => `<div class="relation-row">
        <b>${esc(asset.role)} - ${esc(asset.name)}</b>
        ${esc(asset.type || "asset")} ${asset.weight ? ` / weight ${esc(asset.weight)}` : ""}
        ${asset.reason ? `<p>${esc(asset.reason)}</p>` : asset.summary ? `<p>${esc(asset.summary)}</p>` : ""}
      </div>`).join("");
      if (!systems && !assets) return "";
      return `<div class="section"><h4>Relations</h4>${systems}${assets}</div>`;
    }

    function definitionBlocks(item) {
      const blocks = [];
      blocks.push(`<div class="section"><h4>Definition</h4><p>${esc(item.definition || item.summary || "")}</p></div>`);
      if (item.tags && item.tags.length) blocks.push(`<div class="section"><h4>Tags</h4><div class="chips">${chips(item.tags)}</div></div>`);
      if (item.required_asset_types && item.required_asset_types.length) blocks.push(`<div class="section"><h4>Required Asset Types</h4><div class="chips">${chips(item.required_asset_types, "recipe")}</div></div>`);
      if (item.recommended_aspect_ratios && item.recommended_aspect_ratios.length) blocks.push(`<div class="section"><h4>Aspect Ratios</h4><div class="chips">${chips(item.recommended_aspect_ratios)}</div></div>`);
      blocks.push(listBlock("Use Cases", item.use_cases));
      blocks.push(listBlock("Composition Rules", item.composition_rules));
      blocks.push(listBlock("Visual Rules", item.visual_rules));
      blocks.push(listBlock("Prompt Fragments", item.prompt_fragments));
      blocks.push(listBlock("Negative / Avoid Rules", [...(item.negative_fragments || []), ...(item.avoid_rules || []), ...(item.avoid_with || [])]));
      blocks.push(listBlock("Compatible With", item.compatible_with));
      return blocks.filter(Boolean).join("");
    }

    function currentItems() {
      return (state.data[state.view] || []).filter(matches);
    }

    function sourceView(item) {
      return item.source_view || state.view;
    }

    function favoriteTarget(item) {
      return item.entity_type && item.entity_type !== "visual_asset";
    }

    function favoriteButton(item) {
      if (!favoriteTarget(item)) return "";
      return `<button class="favorite-button ${item.is_favorite ? "active" : ""}" data-entity-type="${attr(item.entity_type)}" data-entity-id="${attr(item.id)}" aria-label="${item.is_favorite ? "Remove from favorites" : "Add to favorites"}">${item.is_favorite ? "&#9733;" : "&#9734;"}</button>`;
    }

    function openDetail(id, view = state.view) {
      state.detail = { view, id };
      render();
    }

    function closeDetail() {
      state.detail = null;
      render();
    }

    function renderList() {
      const items = currentItems();
      document.getElementById("content").innerHTML = `<div class="topline">
        <h2>${esc(labels[state.view])}</h2>
        <div class="count">${items.length} shown</div>
      </div>
      <div class="grid">${items.map(card).join("") || `<div class="error">No matching records.</div>`}</div>`;
      document.querySelectorAll(".card").forEach(cardNode => {
        cardNode.addEventListener("click", () => openDetail(cardNode.dataset.id, cardNode.dataset.sourceView));
        cardNode.addEventListener("keydown", event => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            openDetail(cardNode.dataset.id, cardNode.dataset.sourceView);
          }
        });
      });
      bindFavoriteButtons();
    }

    function renderDetail() {
      const item = (state.data[state.detail.view] || []).find(candidate => candidate.id === state.detail.id);
      if (!item) {
        state.detail = null;
        renderList();
        return;
      }
      const type = item.type || item.kind || "recipe";
      const references = existingImages(item.reference_images);
      const generated = existingImages(item.generated_images);
      document.getElementById("content").innerHTML = `<div class="detail">
        <div class="detail-head">
          <button class="back" id="back">Back</button>
          <div class="detail-title">
            <div>
              <div class="meta">
                <span class="pill ${badgeClasses[state.detail.view]}">${esc(type)}</span>
                ${item.status ? `<span class="pill">${esc(item.status)}</span>` : ""}
                <span class="pill">${esc(references.length)} ref</span>
                <span class="pill">${esc(generated.length)} gen</span>
              </div>
              <h2>${esc(item.name)}</h2>
            </div>
            ${favoriteButton(item)}
          </div>
        </div>
        <div class="detail-top">
          <div class="panel">${definitionBlocks(item)}${relationBlock(item)}</div>
          <div class="detail-media">
            <div class="section">
              <h4>Reference Images</h4>
              ${imageGallery(references, "No reference image")}
            </div>
            <div class="section">
              <h4>Generated Images</h4>
              ${imageGallery(generated, "No generated image")}
            </div>
          </div>
        </div>
      </div>`;
      document.getElementById("back").addEventListener("click", closeDetail);
      bindImageActions();
      bindFavoriteButtons();
    }

    function openLightbox(src, label) {
      const lightbox = document.getElementById("lightbox");
      lightbox.innerHTML = `<div class="lightbox-inner">
        <div class="lightbox-bar">
          <span>${esc(label)}</span>
          <button class="close" id="closeLightbox">Close</button>
        </div>
        <img src="${attr(src)}" alt="${attr(label)}">
        <a class="download" href="${attr(src)}" download="${attr(label)}">Download</a>
      </div>`;
      lightbox.classList.add("active");
      lightbox.setAttribute("aria-hidden", "false");
      document.getElementById("closeLightbox").addEventListener("click", closeLightbox);
      lightbox.addEventListener("click", event => {
        if (event.target === lightbox) closeLightbox();
      }, { once: true });
    }

    function closeLightbox() {
      const lightbox = document.getElementById("lightbox");
      lightbox.classList.remove("active");
      lightbox.setAttribute("aria-hidden", "true");
      lightbox.innerHTML = "";
    }

    function bindImageActions() {
      document.querySelectorAll(".preview").forEach(button => {
        button.addEventListener("click", () => openLightbox(button.dataset.src, button.dataset.label));
      });
    }

    async function refreshData() {
      const response = await fetch("/api/panel-data");
      state.data = await response.json();
      renderStats();
      renderFilters();
    }

    async function toggleFavorite(button) {
      const entityType = button.dataset.entityType;
      const entityId = button.dataset.entityId;
      const item = [...(state.data.recipes || []), ...(state.data.visual_systems || [])]
        .find(candidate => candidate.entity_type === entityType && candidate.id === entityId);
      if (!item) return;
      button.disabled = true;
      try {
        const response = await fetch("/api/favorite", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ entity_type: entityType, entity_id: entityId, favorite: !item.is_favorite })
        });
        if (!response.ok) throw new Error(`Favorite update failed: ${response.status}`);
        await refreshData();
        render();
      } catch (error) {
        console.error(error);
        button.disabled = false;
      }
    }

    function bindFavoriteButtons() {
      document.querySelectorAll(".favorite-button").forEach(button => {
        button.addEventListener("click", event => {
          event.stopPropagation();
          toggleFavorite(button);
        });
      });
    }

    function render() {
      document.querySelectorAll(".tab").forEach(button => button.classList.toggle("active", button.dataset.view === state.view));
      if (state.detail) renderDetail();
      else renderList();
    }

    async function boot() {
      try {
        const response = await fetch("/api/panel-data");
        state.data = await response.json();
        renderStats();
        renderFilters();
        render();
      } catch (error) {
        document.getElementById("content").innerHTML = `<div class="error">${esc(error.message)}</div>`;
      }
    }

    document.querySelectorAll(".tab").forEach(button => button.addEventListener("click", () => {
      state.view = button.dataset.view;
      state.detail = null;
      render();
    }));
    document.getElementById("search").addEventListener("input", event => {
      state.q = event.target.value;
      state.detail = null;
      render();
    });
    document.getElementById("type").addEventListener("change", event => {
      state.type = event.target.value;
      state.detail = null;
      render();
    });
    document.getElementById("status").addEventListener("change", event => {
      state.status = event.target.value;
      state.detail = null;
      render();
    });
    document.addEventListener("keydown", event => {
      if (event.key === "Escape") {
        if (document.getElementById("lightbox").classList.contains("active")) closeLightbox();
        else if (state.detail) closeDetail();
      }
    });
    boot();
  </script>
</body>
</html>
"""
