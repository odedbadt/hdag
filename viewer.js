(() => {
  // ── State ────────────────────────────────────────────────────────────────────
  let tx = 0, ty = 0, scale = 1;
  let hdagMeta = null;   // { nodes: {id→type}, types: {...} }
  let isDragging = false, dragStartX = 0, dragStartY = 0, dragTx = 0, dragTy = 0;

  // ── DOM refs ──────────────────────────────────────────────────────────────────
  const container   = document.getElementById("svg-container");
  const fileInput   = document.getElementById("file-input");
  const btnReset    = document.getElementById("btn-reset");
  const overlay     = document.getElementById("modal-overlay");
  const modalBody   = document.getElementById("modal-body");
  const modalClose  = document.getElementById("modal-close");
  const emptyState  = document.getElementById("empty-state");

  // ── Pan/Zoom helpers ─────────────────────────────────────────────────────────

  function getWrapper() { return document.getElementById("svg-wrapper"); }

  function applyTransform() {
    const w = getWrapper();
    if (w) w.style.transform = `translate(${tx}px,${ty}px) scale(${scale})`;
  }

  function resetView() {
    const w = getWrapper();
    if (!w) return;
    const svgEl = w.querySelector("svg");
    if (!svgEl) return;
    const cw = container.clientWidth, ch = container.clientHeight;
    // Prefer explicit px dimensions we set; fall back to viewBox; fall back to container
    const vb = svgEl.viewBox.baseVal;
    const sw = parseFloat(svgEl.getAttribute("width"))  || (vb && vb.width)  || cw;
    const sh = parseFloat(svgEl.getAttribute("height")) || (vb && vb.height) || ch;
    const pad = 40;
    scale = Math.min((cw - pad) / sw, (ch - pad) / sh, 1);
    tx = (cw - sw * scale) / 2;
    ty = (ch - sh * scale) / 2;
    applyTransform();
  }

  // ── File loading ──────────────────────────────────────────────────────────────

  fileInput.addEventListener("change", () => {
    const file = fileInput.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = e => loadSVG(e.target.result);
    reader.readAsText(file);
  });

  function loadSVG(svgText) {
    // Strip XML declaration and DOCTYPE — both break innerHTML parsing
    const cleaned = svgText
      .replace(/<\?xml[^?]*\?>/i, "")
      .replace(/<!DOCTYPE[^>]*>/i, "");

    // Remove old wrapper
    const old = getWrapper();
    if (old) old.remove();
    if (emptyState) emptyState.style.display = "none";

    // Create wrapper div to hold the SVG
    const wrapper = document.createElement("div");
    wrapper.id = "svg-wrapper";
    wrapper.innerHTML = cleaned;
    container.appendChild(wrapper);

    // Extract embedded metadata
    hdagMeta = null;
    const scriptTag = wrapper.querySelector('script[id="hdag-data"]');
    if (scriptTag) {
      try { hdagMeta = JSON.parse(scriptTag.textContent); } catch(e) { console.warn("hdag-data parse error", e); }
    }

    // Set pixel dimensions from viewBox (Graphviz emits "pt" units which
    // report 0 via .baseVal.value in some browsers)
    const svgEl = wrapper.querySelector("svg");
    if (svgEl) {
      const vb = svgEl.viewBox.baseVal;
      if (vb && vb.width) {
        svgEl.setAttribute("width",  vb.width  + "px");
        svgEl.setAttribute("height", vb.height + "px");
      } else {
        svgEl.removeAttribute("width");
        svgEl.removeAttribute("height");
      }
    }

    resetView();
  }

  btnReset.addEventListener("click", resetView);

  // Auto-load: check ?svg= param, fall back to my_graph.svg
  (function autoLoad() {
    const params = new URLSearchParams(location.search);
    const svgUrl = params.get("svg") || "my_graph.svg";
    fetch(svgUrl)
      .then(r => { if (!r.ok) throw new Error(r.status); return r.text(); })
      .then(text => loadSVG(text))
      .catch(() => { /* no auto-load, show empty state */ });
  })();

  // ── Wheel: pan + zoom ─────────────────────────────────────────────────────────

  container.addEventListener("wheel", e => {
    e.preventDefault();
    const delta = e.deltaY;

    if (e.ctrlKey) {
      // Zoom anchored at mouse
      const rect = container.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const factor = delta < 0 ? 1.1 : 1 / 1.1;
      const newScale = Math.min(Math.max(scale * factor, 0.05), 20);
      const f = newScale / scale;
      tx = mx - (mx - tx) * f;
      ty = my - (my - ty) * f;
      scale = newScale;
    } else if (e.shiftKey) {
      // Horizontal pan
      tx -= delta;
    } else {
      // Vertical pan
      ty -= delta;
    }
    applyTransform();
  }, { passive: false });

  // ── Drag to pan ───────────────────────────────────────────────────────────────

  container.addEventListener("mousedown", e => {
    if (e.button !== 0) return;
    isDragging = true;
    dragStartX = e.clientX;
    dragStartY = e.clientY;
    dragTx = tx;
    dragTy = ty;
    container.classList.add("grabbing");
  });

  window.addEventListener("mousemove", e => {
    if (!isDragging) return;
    tx = dragTx + (e.clientX - dragStartX);
    ty = dragTy + (e.clientY - dragStartY);
    applyTransform();
  });

  window.addEventListener("mouseup", () => {
    isDragging = false;
    container.classList.remove("grabbing");
  });

  // ── Click → modal ─────────────────────────────────────────────────────────────

  container.addEventListener("click", e => {
    if (isDragging) return;
    const nodeGroup = e.target.closest("g.node");
    if (!nodeGroup) return;

    const titleEl = nodeGroup.querySelector("title");
    if (!titleEl) return;
    const nodeId = titleEl.textContent.trim();

    showModal(nodeId);
  });

  function showModal(nodeId) {
    const typeName = hdagMeta?.nodes?.[nodeId];
    const typeDef  = typeName && hdagMeta?.types?.[typeName];

    const parts   = nodeId.split(".");
    const display = parts.slice(1).join(".") || nodeId;
    const parent  = parts.length > 2 ? parts.slice(1, -1).join(".") : null;
    const parentType = parent && hdagMeta?.nodes?.["root." + parent];

    const rows = [];

    rows.push(["Node ID", `<code>${nodeId}</code>`]);
    rows.push(["Display", `<strong>${display}</strong>`]);

    if (typeName) rows.push(["Type", typeName]);

    if (typeDef?.ports?.in?.length) {
      rows.push(["In ports",  typeDef.ports.in.map(p  => `<span class="port-tag">${p}</span>`).join(" ")]);
    }
    if (typeDef?.ports?.out?.length) {
      rows.push(["Out ports", typeDef.ports.out.map(p => `<span class="port-tag">${p}</span>`).join(" ")]);
    }

    if (typeDef?.children) {
      const childList = Object.entries(typeDef.children)
        .map(([n, t]) => `<span class="port-tag">${n}: ${t}</span>`).join(" ");
      rows.push(["Children", childList]);
    }

    if (parent) rows.push(["Parent", parent + (parentType ? ` [${parentType}]` : "")]);

    const breadcrumb = parts.join(" › ");
    rows.push(["Path", `<small>${breadcrumb}</small>`]);

    const tableHTML = rows.map(([k, v]) =>
      `<tr><td>${k}</td><td>${v}</td></tr>`
    ).join("");

    modalBody.innerHTML = `<h2>${display}</h2><table>${tableHTML}</table>`;
    overlay.classList.remove("hidden");
  }

  // ── Modal close ───────────────────────────────────────────────────────────────

  modalClose.addEventListener("click", closeModal);
  overlay.addEventListener("click", e => { if (e.target === overlay) closeModal(); });
  document.addEventListener("keydown", e => { if (e.key === "Escape") closeModal(); });

  function closeModal() { overlay.classList.add("hidden"); }
})();
