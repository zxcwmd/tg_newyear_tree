const tg = window.Telegram?.WebApp;
if (tg) { tg.ready(); tg.expand(); }

const params = new URLSearchParams(window.location.search);
const chatId = params.get("chat_id") || params.get("startapp") || tg?.initDataUnsafe?.start_param || "1";
const initData = tg?.initData || "";

let state = {
  ornaments: {},
  selectedType: "ball",
  selectedColor: "red",
  decorations: [],
  stats: [],
  myUserId: tg?.initDataUnsafe?.user?.id || 0,
};

let dragState = null;
let suppressNextTreeClick = false;

const $ = (s) => document.querySelector(s);
const treeSvg = $("#treeSvg");
const decorLayer = $("#decorLayer");
const palette = $("#palette");

function toast(msg, isError = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast show" + (isError ? " error" : "");
  setTimeout(() => t.classList.remove("show"), 2200);
}

function haptic(type = "light") {
  try { tg?.HapticFeedback?.impactOccurred(type); } catch (e) {}
}

function updateCountdown() {
  const now = new Date();
  const nextYear = now.getMonth() === 0 && now.getDate() === 1
    ? now.getFullYear()
    : now.getFullYear() + 1;
  const target = new Date(nextYear, 0, 1, 0, 0, 0);
  const diff = target - now;
  const el = $("#countdown");
  if (!el) return;
  if (diff <= 0) {
    el.textContent = "🎉 С Новым годом!";
    return;
  }
  const days = Math.floor(diff / (1000 * 60 * 60 * 24));
  const hours = Math.floor((diff / (1000 * 60 * 60)) % 24);
  const mins = Math.floor((diff / (1000 * 60)) % 60);
  el.textContent = `⏳ До 1 января: ${days}д ${hours}ч ${mins}м`;
}

// --- SVG helpers ---
function svgEl(tag, attrs = {}) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  return el;
}

function drawSnow() {
  const g = $("#snow");
  g.innerHTML = "";
  for (let i = 0; i < 40; i++) {
    const x = Math.random() * 400, y = Math.random() * 500;
    const r = Math.random() * 2 + 0.8;
    g.appendChild(svgEl("circle", { cx: x, cy: y, r, fill: "#fff", opacity: 0.4 + Math.random() * 0.5 }));
  }
}

function drawTopStar() {
  const g = $("#topStar");
  g.innerHTML = "";
  g.appendChild(starShape(200, 45, 22, "#ffd60a"));
}

function starShape(cx, cy, r, color) {
  let pts = "";
  for (let i = 0; i < 10; i++) {
    const a = -Math.PI / 2 + i * Math.PI / 5;
    const rad = i % 2 === 0 ? r : r * 0.45;
    pts += `${cx + rad * Math.cos(a)},${cy + rad * Math.sin(a)} `;
  }
  return svgEl("polygon", { points: pts, fill: color, stroke: "#b45309", "stroke-width": 1 });
}

function ornamentShape(type, color, x, y) {
  const g = svgEl("g", { class: "dec-item" });
  g.setAttribute("transform", `translate(${x},${y})`);
  if (type === "ball") {
    g.appendChild(svgEl("rect", { x: -3, y: -16, width: 6, height: 6, fill: "#cbd5e1" }));
    g.appendChild(svgEl("circle", { cx: 0, cy: 0, r: 12, fill: color, stroke: "rgba(0,0,0,.4)" }));
    g.appendChild(svgEl("ellipse", { cx: -4, cy: -5, rx: 4, ry: 3, fill: "#fff", opacity: 0.7 }));
  } else if (type === "star") {
    g.appendChild(starShape(0, 0, 14, color));
  } else if (type === "snowflake") {
    for (let a = 0; a < 360; a += 60) {
      const rad = a * Math.PI / 180;
      g.appendChild(svgEl("line", {
        x1: 0, y1: 0, x2: 11 * Math.cos(rad), y2: 11 * Math.sin(rad),
        stroke: color, "stroke-width": 2.5, "stroke-linecap": "round"
      }));
    }
    g.appendChild(svgEl("circle", { cx: 0, cy: 0, r: 2.5, fill: color }));
  } else if (type === "gift") {
    g.appendChild(svgEl("rect", { x: -11, y: -7, width: 22, height: 18, fill: color, stroke: "rgba(0,0,0,.4)", rx: 2 }));
    g.appendChild(svgEl("rect", { x: -11, y: -11, width: 22, height: 6, fill: color, stroke: "rgba(0,0,0,.4)", rx: 2 }));
    g.appendChild(svgEl("rect", { x: -2, y: -11, width: 4, height: 22, fill: "#ffd60a" }));
  } else if (type === "bell") {
    g.appendChild(svgEl("path", { d: "M -10 6 A 10 10 0 0 1 10 6 Z", fill: color, stroke: "rgba(0,0,0,.4)" }));
    g.appendChild(svgEl("rect", { x: -10, y: 5, width: 20, height: 4, fill: color }));
    g.appendChild(svgEl("circle", { cx: 0, cy: 10, r: 3, fill: "#92400e" }));
  } else if (type === "candy") {
    g.appendChild(svgEl("polygon", { points: "-8,0 -16,-6 -16,6", fill: color }));
    g.appendChild(svgEl("polygon", { points: "8,0 16,-6 16,6", fill: color }));
    g.appendChild(svgEl("circle", { cx: 0, cy: 0, r: 8, fill: color, stroke: "rgba(0,0,0,.4)" }));
    g.appendChild(svgEl("line", { x1: -4, y1: -5, x2: 4, y2: 5, stroke: "#fff", "stroke-width": 2 }));
  }
  return g;
}

function clientToPercent(clientX, clientY) {
  const rect = treeSvg.getBoundingClientRect();
  const x = Math.max(4, Math.min(96, (clientX - rect.left) / rect.width * 100));
  const y = Math.max(6, Math.min(92, (clientY - rect.top) / rect.height * 100));
  return {
    x: Math.round(x * 10) / 10,
    y: Math.round(y * 10) / 10,
  };
}

function renderDecorations() {
  decorLayer.innerHTML = "";
  for (const d of state.decorations) {
    const colorHex = state.ornaments[d.ornament_type]?.colors?.[d.color] || "#e63946";
    const x = d.x / 100 * 400;
    const y = d.y / 100 * 500;
    const el = ornamentShape(d.ornament_type, colorHex, x, y);
    el.dataset.id = d.id;

    el.addEventListener("pointerdown", (e) => {
      e.stopPropagation();
      if (state.myUserId && d.user_id !== state.myUserId) {
        toast("Это игрушка другого участника 🙂");
        return;
      }
      el.setPointerCapture(e.pointerId);
      dragState = {
        dec: d,
        el,
        startX: e.clientX,
        startY: e.clientY,
        moved: false,
        curX: d.x,
        curY: d.y,
      };
    });

    el.addEventListener("pointermove", (e) => {
      if (!dragState || dragState.dec.id !== d.id) return;
      const dist = Math.hypot(e.clientX - dragState.startX, e.clientY - dragState.startY);
      if (dist > 6) dragState.moved = true;
      if (dragState.moved) {
        const pt = clientToPercent(e.clientX, e.clientY);
        dragState.curX = pt.x;
        dragState.curY = pt.y;
        el.setAttribute("transform", `translate(${pt.x / 100 * 400},${pt.y / 100 * 500})`);
      }
    });

    el.addEventListener("pointerup", async (e) => {
      if (!dragState || dragState.dec.id !== d.id) return;
      e.stopPropagation();
      suppressNextTreeClick = true;
      setTimeout(() => { suppressNextTreeClick = false; }, 80);
      const finishedDrag = dragState;
      dragState = null;
      if (finishedDrag.moved) {
        await saveMoveDecoration(d.id, finishedDrag.curX, finishedDrag.curY);
      } else {
        await onDecorationClick(d);
      }
    });

    decorLayer.appendChild(el);
  }
  $("#counter").textContent = `Игрушек: ${state.decorations.length}`;
}

async function saveMoveDecoration(decorationId, x, y) {
  try {
    const res = await fetch("/api/move", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decoration_id: decorationId, x, y, init_data: initData }),
    });
    if (!res.ok) throw new Error();
    haptic("light");
    toast("Игрушка перемещена ✨");
    loadTree();
  } catch {
    toast("Не удалось переместить", true);
    loadTree();
  }
}

function renderStats() {
  const ul = $("#statsList");
  ul.innerHTML = "";
  if (!state.stats.length) {
    ul.innerHTML = "<li><span>Пока никто не украшал</span><span>—</span></li>";
    return;
  }
  state.stats.forEach((s, i) => {
    const name = s.username ? `@${s.username}` : (s.first_name || "Участник");
    const medal = ["🥇", "🥈", "🥉"][i] || `${i + 1}.`;
    const li = document.createElement("li");
    li.innerHTML = `<span>${medal} ${escapeHtml(name)}</span><b>${s.count} шт.</b>`;
    ul.appendChild(li);
  });
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

function renderPalette() {
  palette.innerHTML = "";
  for (const [type, info] of Object.entries(state.ornaments)) {
    const btn = document.createElement("button");
    btn.className = "ornament-btn" + (type === state.selectedType ? " selected" : "");
    btn.innerHTML = `<span class="emoji">${info.emoji}</span><span class="name">${info.name}</span>`;
    btn.onclick = () => {
      state.selectedType = type;
      state.selectedColor = Object.keys(info.colors)[0];
      haptic("light");
      renderPalette();
    };
    palette.appendChild(btn);
  }
  const colorsDiv = document.createElement("div");
  colorsDiv.className = "colors";
  colorsDiv.style.width = "100%";
  colorsDiv.style.justifyContent = "center";
  const info = state.ornaments[state.selectedType];
  if (info) {
    for (const [cname, hex] of Object.entries(info.colors)) {
      const dot = document.createElement("button");
      dot.className = "color-dot" + (cname === state.selectedColor ? " selected" : "");
      dot.style.background = hex;
      dot.title = cname;
      dot.onclick = () => { state.selectedColor = cname; haptic("light"); renderPalette(); };
      colorsDiv.appendChild(dot);
    }
  }
  palette.appendChild(colorsDiv);
}

async function loadTree() {
  try {
    const res = await fetch(`/api/tree/${chatId}`);
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    state.ornaments = data.ornaments;
    state.decorations = data.decorations;
    state.stats = data.stats;
    $("#chatTitle").textContent = data.tree.chat_title ? `Чат: ${data.tree.chat_title}` : "Общая ёлка чата";
    if (data.tree.is_finished) {
      $("#hint").textContent = "🎉 Ивент завершён! С Новым годом!";
    }
    renderPalette();
    renderDecorations();
    renderStats();
  } catch (e) {
    $("#chatTitle").textContent = "Не удалось загрузить ёлку 😢";
    toast("Ошибка загрузки", true);
  }
}

async function onDecorationClick(d) {
  if (state.myUserId && d.user_id !== state.myUserId) {
    toast("Это чужая игрушка 🙂");
    return;
  }
  if (!confirm("Снять эту игрушку с ёлки?")) return;
  try {
    const res = await fetch("/api/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decoration_id: d.id, init_data: initData }),
    });
    if (!res.ok) throw new Error();
    toast("Игрушка снята");
    haptic("medium");
    loadTree();
  } catch {
    toast("Не удалось снять", true);
  }
}

treeSvg.addEventListener("click", async (e) => {
  if (suppressNextTreeClick) return;
  if (e.target.closest(".dec-item")) return;
  const pt = clientToPercent(e.clientX, e.clientY);
  try {
    const res = await fetch("/api/decorate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chat_id: Number(chatId),
        ornament_type: state.selectedType,
        color: state.selectedColor,
        x: pt.x,
        y: pt.y,
        init_data: initData,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Ошибка");
    }
    haptic("medium");
    toast("Игрушка повешена! 🎄");
    loadTree();
  } catch (err) {
    toast(err.message || "Не удалось повесить", true);
  }
});

$("#previewBtn").addEventListener("click", () => {
  $("#previewImg").src = `/api/final-image/${chatId}?t=${Date.now()}`;
  $("#previewModal").classList.remove("hidden");
});

$("#closeModalBtn").addEventListener("click", () => {
  $("#previewModal").classList.add("hidden");
});

$("#previewModal").addEventListener("click", (e) => {
  if (e.target === $("#previewModal")) {
    $("#previewModal").classList.add("hidden");
  }
});

drawSnow();
drawTopStar();
updateCountdown();
setInterval(updateCountdown, 30000);
loadTree();
