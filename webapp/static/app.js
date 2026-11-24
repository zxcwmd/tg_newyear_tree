const tg = window.Telegram?.WebApp;
if (tg) {
  tg.ready();
  tg.expand();
}

const params = new URLSearchParams(window.location.search);
const rawUrlChat = params.get("chat_id") || params.get("startapp") || tg?.initDataUnsafe?.start_param || "";
// Групповые чаты имеют отрицательный ID (< 0). Одиночные положительные ID (> 1) объединяем в общую ёлку "1"
function normalizeChatId(val) {
  const n = Number(val);
  if (!Number.isNaN(n) && n < 0) return String(n);
  return "1";
}

const chatId = normalizeChatId(rawUrlChat);
const initData = tg?.initData || "";

function getPersistentUser() {
  const tgUser = tg?.initDataUnsafe?.user;
  if (tgUser && tgUser.id) {
    return {
      id: Number(tgUser.id),
      username: tgUser.username || "",
      first_name: tgUser.first_name || "Игрок",
      last_name: tgUser.last_name || "",
    };
  }
  try {
    const raw = localStorage.getItem("ny_local_user");
    if (raw) return JSON.parse(raw);
  } catch (e) {}
  const fallback = {
    id: 100000 + Math.floor(Math.random() * 899999),
    username: "",
    first_name: "Игрок",
    last_name: "",
  };
  try { localStorage.setItem("ny_local_user", JSON.stringify(fallback)); } catch (e) {}
  return fallback;
}

const currentUser = getPersistentUser();
const BACKUP_KEY = `ny_backup_v5_${chatId}_${currentUser.id}`;

let state = {
  ornaments: {},
  donatePacks: {},
  gramWallet: "",
  selectedType: "ball",
  selectedColor: "red",
  decorations: [],
  stats: [],
  leaderboard: { by_toys: [], by_coins: [] },
  activeLbTab: "by_toys",
  myUserId: currentUser.id,
  coins: 50,
  clickPower: 1,
  inventory: { ball: 2, snowflake: 1 },
  energy: 500,
  maxEnergy: 500,
  pendingClicks: 0,
  combo: 1,
  lastClickAt: 0,
  activeGramPack: null,
};

let dragState = null;
let suppressNextTreeClick = false;
let clickFlushTimer = null;

const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);
const treeSvg = $("#treeSvg");
const decorLayer = $("#decorLayer");
const palette = $("#palette");

function toast(msg, isError = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast show" + (isError ? " error" : "");
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => t.classList.remove("show"), 2300);
}

function haptic(type = "light") {
  try { tg?.HapticFeedback?.impactOccurred(type); } catch (e) {}
}

// ============================================================================
// 1. ЖИВОЙ ФОН (#bgCanvas) И СИСТЕМА ЧАСТИЦ (#fxCanvas)
// ============================================================================
const bgCanvas = $("#bgCanvas");
const bgCtx = bgCanvas.getContext("2d");
const fxCanvas = $("#fxCanvas");
const fxCtx = fxCanvas.getContext("2d");

let bgW = window.innerWidth;
let bgH = window.innerHeight;
const bgSnow = [];
const fxParticles = [];

function resizeCanvases() {
  bgW = window.innerWidth;
  bgH = window.innerHeight;
  bgCanvas.width = bgW;
  bgCanvas.height = bgH;
  fxCanvas.width = bgW;
  fxCanvas.height = bgH;
}
window.addEventListener("resize", resizeCanvases);
resizeCanvases();

for (let i = 0; i < 65; i++) {
  bgSnow.push({
    x: Math.random() * bgW,
    y: Math.random() * bgH,
    r: Math.random() * 2.4 + 0.7,
    vy: Math.random() * 0.65 + 0.25,
    vx: (Math.random() - 0.5) * 0.35,
    phase: Math.random() * Math.PI * 2,
    alpha: Math.random() * 0.55 + 0.25,
  });
}

function spawnParticles(clientX, clientY, color = "#fde047", count = 18) {
  const paletteColors = [color, "#fde047", "#38bdf8", "#ffffff", "#f43f5e", "#34d399"];
  for (let i = 0; i < count; i++) {
    const angle = Math.random() * Math.PI * 2;
    const speed = Math.random() * 5.2 + 1.4;
    fxParticles.push({
      x: clientX,
      y: clientY,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed - 1.5,
      size: Math.random() * 4.5 + 2.2,
      color: paletteColors[i % paletteColors.length],
      alpha: 1,
      decay: Math.random() * 0.024 + 0.018,
      star: i % 3 === 0,
    });
  }
}

let animTick = 0;
function animateCanvases() {
  animTick += 0.015;
  bgCtx.clearRect(0, 0, bgW, bgH);

  // Мягкое северное сияние в фоне
  const grad1 = bgCtx.createRadialGradient(
    bgW * (0.3 + 0.15 * Math.sin(animTick)),
    bgH * 0.18,
    10,
    bgW * 0.5,
    bgH * 0.25,
    bgW * 0.85
  );
  grad1.addColorStop(0, "rgba(16, 185, 129, 0.16)");
  grad1.addColorStop(0.5, "rgba(14, 165, 233, 0.10)");
  grad1.addColorStop(1, "rgba(4, 9, 20, 0)");
  bgCtx.fillStyle = grad1;
  bgCtx.fillRect(0, 0, bgW, bgH);

  // Падающий снег с глубиной
  for (const s of bgSnow) {
    s.y += s.vy;
    s.x += s.vx + Math.sin(animTick + s.phase) * 0.25;
    if (s.y > bgH + 6) {
      s.y = -6;
      s.x = Math.random() * bgW;
    }
    if (s.x > bgW + 6) s.x = -6;
    if (s.x < -6) s.x = bgW + 6;

    bgCtx.beginPath();
    bgCtx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
    bgCtx.fillStyle = `rgba(255, 255, 255, ${s.alpha})`;
    bgCtx.fill();
  }

  // Частицы спецэффектов
  fxCtx.clearRect(0, 0, bgW, bgH);
  for (let i = fxParticles.length - 1; i >= 0; i--) {
    const p = fxParticles[i];
    p.x += p.vx;
    p.y += p.vy;
    p.vy += 0.14; // гравитация
    p.alpha -= p.decay;
    if (p.alpha <= 0) {
      fxParticles.splice(i, 1);
      continue;
    }
    fxCtx.save();
    fxCtx.globalAlpha = Math.max(0, p.alpha);
    fxCtx.fillStyle = p.color;
    fxCtx.shadowColor = p.color;
    fxCtx.shadowBlur = 8;
    if (p.star) {
      fxCtx.translate(p.x, p.y);
      fxCtx.rotate(p.alpha * 4);
      fxCtx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size);
    } else {
      fxCtx.beginPath();
      fxCtx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
      fxCtx.fill();
    }
    fxCtx.restore();
  }

  requestAnimationFrame(animateCanvases);
}
requestAnimationFrame(animateCanvases);

// ============================================================================
// 2. ПРОВЕРКА ГРАНИЦ ЁЛКИ (ЗАПРЕТ ВЕШАТЬ МИМО ВЕТОК)
// ============================================================================
const TREE_TIERS = [
  [64.0, 215.0, 8.0, 74.0],
  [150.0, 325.0, 14.0, 94.0],
  [240.0, 428.0, 18.0, 118.0],
];

function isPointInsideTree(xPct, yPct) {
  const sx = xPct * 4.0;
  const sy = yPct * 5.0;
  for (const [yTop, yBot, hwTop, hwBot] of TREE_TIERS) {
    if (sy >= yTop && sy <= yBot) {
      const t = (sy - yTop) / (yBot - yTop);
      const maxHw = hwTop + t * (hwBot - hwTop);
      if (Math.abs(sx - 200.0) <= maxHw) return true;
    }
  }
  return false;
}

function clampToTree(xPct, yPct) {
  const sx = xPct * 4.0;
  const sy = Math.max(68.0, Math.min(424.0, yPct * 5.0));
  let allowedHw = 20.0;
  for (const [yTop, yBot, hwTop, hwBot] of TREE_TIERS) {
    if (sy >= yTop && sy <= yBot) {
      const t = (sy - yTop) / (yBot - yTop);
      const hw = hwTop + t * (hwBot - hwTop) - 3.0;
      if (hw > allowedHw) allowedHw = hw;
    }
  }
  const clampedSx = Math.max(200.0 - allowedHw, Math.min(200.0 + allowedHw, sx));
  return {
    x: Math.round((clampedSx / 4.0) * 10) / 10,
    y: Math.round((sy / 5.0) * 10) / 10,
  };
}

// ============================================================================
// 3. ЛОКАЛЬНЫЙ И ОБЛАЧНЫЙ БЭКАП ПРОГРЕССА
// ============================================================================
function saveBackup() {
  const myDecs = state.decorations.filter((d) => d.user_id === state.myUserId);
  const payload = {
    coins: state.coins,
    click_power: state.clickPower,
    inventory: state.inventory,
    decorations: myDecs,
    ts: Date.now(),
  };
  const jsonStr = JSON.stringify(payload);
  try {
    localStorage.setItem(BACKUP_KEY, jsonStr);
  } catch (e) {}
  try {
    if (tg?.CloudStorage?.setItem) {
      tg.CloudStorage.setItem(BACKUP_KEY, jsonStr, () => {});
    }
  } catch (e) {}
}

function loadLocalBackup() {
  try {
    const raw = localStorage.getItem(BACKUP_KEY);
    if (raw) return JSON.parse(raw);
  } catch (e) {}
  return null;
}

// ============================================================================
// 4. НАВИГАЦИЯ ПО ВКЛАДКАМ
// ============================================================================
function switchTab(tabName) {
  $$(".tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === tabName));
  $$(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${tabName}`));
  haptic("light");
  if (tabName === "leaderboard") {
    fetchLeaderboardOnly();
  }
}

$$(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});

$("#balancePill").addEventListener("click", () => switchTab("clicker"));

$$(".lb-subtab").forEach((btn) => {
  btn.addEventListener("click", () => {
    state.activeLbTab = btn.dataset.lb;
    $$(".lb-subtab").forEach((b) => b.classList.toggle("active", b.dataset.lb === state.activeLbTab));
    haptic("light");
    renderLeaderboard();
  });
});

$("#refreshLbBtn").addEventListener("click", async () => {
  haptic("light");
  await fetchLeaderboardOnly(true);
});

async function fetchLeaderboardOnly(showToast = false) {
  try {
    const res = await fetch(`/api/leaderboard?chat_id=${chatId}&t=${Date.now()}`, { cache: "no-store" });
    if (!res.ok) return;
    const data = await res.json();
    state.stats = data.chat_stats || state.stats;
    state.leaderboard = {
      by_toys: data.by_toys || [],
      by_coins: data.by_coins || [],
    };
    renderLeaderboard();
    if (showToast) toast("Рейтинг обновлён 🏆");
  } catch (e) {}
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

function applyProfile(profile) {
  if (!profile) return;
  state.coins = Number(profile.coins ?? state.coins);
  state.clickPower = Number(profile.click_power ?? state.clickPower);
  if (profile.inventory) {
    state.inventory = { ...state.inventory, ...profile.inventory };
  }
  updateHeaderAndClickerUI();
  renderPalette();
  renderShop();
  saveBackup();
}

function updateHeaderAndClickerUI() {
  $("#coinBalance").textContent = state.coins;
  $("#clickerCoins").textContent = `${state.coins} 🪙`;
  $("#clickPowerLabel").textContent = `+${state.clickPower} 🪙`;
  $("#upgradeCost").textContent = state.clickPower * 100;
  $("#energyText").textContent = `${state.energy} / ${state.maxEnergy}`;
  const pct = Math.max(0, Math.min(100, (state.energy / state.maxEnergy) * 100));
  $("#energyBarFill").style.width = `${pct}%`;
  const totalPlayers = Math.max(1, state.leaderboard?.by_toys?.length || state.stats?.length || 1);
  $("#playersCountChip").textContent = `👥 Игроков: ${totalPlayers}`;
}

// ============================================================================
// 5. ТЕКСТУРИРОВАННАЯ 3D ОТРИСОВКА ЁЛКИ, ГИРЛЯНДЫ И ИГРУШЕК
// ============================================================================
function svgEl(tag, attrs = {}) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  return el;
}

function drawSnowAndStars() {
  const g = $("#snow");
  g.innerHTML = "";
  for (let i = 0; i < 36; i++) {
    const x = Math.random() * 400;
    const y = Math.random() * 440;
    const r = Math.random() * 1.8 + 0.6;
    g.appendChild(svgEl("circle", {
      cx: x,
      cy: y,
      r,
      fill: i % 5 === 0 ? "#fef08a" : "#ffffff",
      opacity: 0.35 + Math.random() * 0.55,
    }));
  }
}

function drawGarlandLights() {
  const g = $("#garlandLights");
  g.innerHTML = "";
  const colors = ["#fde047", "#f43f5e", "#38bdf8", "#34d399", "#c084fc"];
  const wires = [
    { x1: 140, y1: 165, cx: 200, cy: 198, x2: 260, y2: 160, count: 5 },
    { x1: 114, y1: 272, cx: 200, cy: 312, x2: 286, y2: 266, count: 6 },
    { x1: 88, y1: 378, cx: 200, cy: 422, x2: 312, y2: 370, count: 7 },
  ];
  let idx = 0;
  for (const w of wires) {
    for (let i = 0; i < w.count; i++) {
      const t = (i + 0.5) / w.count;
      const x = (1 - t) * (1 - t) * w.x1 + 2 * (1 - t) * t * w.cx + t * t * w.x2;
      const y = (1 - t) * (1 - t) * w.y1 + 2 * (1 - t) * t * w.cy + t * t * w.y2;
      const col = colors[idx % colors.length];
      const bulb = svgEl("circle", {
        cx: x,
        cy: y + 2,
        r: 4,
        fill: col,
        class: "garland-bulb",
        style: `animation-delay: ${(idx * 0.23).toFixed(2)}s`,
      });
      g.appendChild(bulb);
      idx++;
    }
  }
}

function drawTopStar() {
  const g = $("#topStar");
  g.innerHTML = "";
  // Сияющий ореол вокруг макушки
  g.appendChild(svgEl("circle", { cx: 200, cy: 48, r: 28, fill: "#fde047", opacity: 0.22, filter: "url(#glowFilter)" }));
  g.appendChild(starShape(200, 48, 24, "#fde047", "#ca8a04"));
  g.appendChild(starShape(200, 48, 12, "#fef9c3", "none"));
}

function starShape(cx, cy, r, fillColor, strokeColor = "#b45309") {
  let pts = "";
  for (let i = 0; i < 10; i++) {
    const a = -Math.PI / 2 + i * Math.PI / 5;
    const rad = i % 2 === 0 ? r : r * 0.44;
    pts += `${cx + rad * Math.cos(a)},${cy + rad * Math.sin(a)} `;
  }
  return svgEl("polygon", {
    points: pts,
    fill: fillColor,
    stroke: strokeColor,
    "stroke-width": strokeColor === "none" ? 0 : 1.2,
  });
}

function ornamentShape(type, colorName, colorHex, x, y) {
  const g = svgEl("g", { class: "dec-item", filter: "url(#softShadow)" });
  g.setAttribute("transform", `translate(${x},${y})`);

  if (type === "ball") {
    const gradId = `ball_${colorName}`;
    const fillVal = document.getElementById(gradId) ? `url(#${gradId})` : colorHex;
    // Золотая петелька и коронка
    g.appendChild(svgEl("circle", { cx: 0, cy: -16, r: 3, fill: "none", stroke: "#facc15", "stroke-width": 1.3 }));
    g.appendChild(svgEl("rect", { x: -3.5, y: -14.5, width: 7, height: 4.5, rx: 1.2, fill: "#eab308", stroke: "#713f12", "stroke-width": 0.6 }));
    // 3D сфера шара
    g.appendChild(svgEl("circle", { cx: 0, cy: 0, r: 12.5, fill: fillVal, stroke: "rgba(255,255,255,0.22)", "stroke-width": 0.7 }));
    // Блик стекла
    g.appendChild(svgEl("ellipse", { cx: -4.2, cy: -4.8, rx: 3.8, ry: 2.2, fill: "#ffffff", opacity: 0.75, transform: "rotate(-25 -4.2 -4.8)" }));
    g.appendChild(svgEl("circle", { cx: -1.5, cy: -1.5, r: 1.1, fill: "#ffffff", opacity: 0.55 }));
  } else if (type === "star") {
    g.appendChild(starShape(0, 0, 15.5, colorHex, "#92400e"));
    g.appendChild(starShape(0, 0, 8, "#ffffff", "none"));
  } else if (type === "snowflake") {
    g.appendChild(svgEl("circle", { cx: 0, cy: 0, r: 13, fill: colorHex, opacity: 0.16 }));
    for (let a = 0; a < 360; a += 60) {
      const rad = (a * Math.PI) / 180;
      const x2 = 12.5 * Math.cos(rad);
      const y2 = 12.5 * Math.sin(rad);
      g.appendChild(svgEl("line", {
        x1: 0, y1: 0, x2, y2,
        stroke: colorHex, "stroke-width": 2.3, "stroke-linecap": "round",
      }));
      const bx = 7.5 * Math.cos(rad);
      const by = 7.5 * Math.sin(rad);
      for (const da of [-35, 35]) {
        const r2 = rad + (da * Math.PI) / 180;
        g.appendChild(svgEl("line", {
          x1: bx, y1: by,
          x2: bx + 4.2 * Math.cos(r2),
          y2: by + 4.2 * Math.sin(r2),
          stroke: colorHex, "stroke-width": 1.6, "stroke-linecap": "round",
        }));
      }
    }
    g.appendChild(svgEl("circle", { cx: 0, cy: 0, r: 3, fill: "#ffffff" }));
  } else if (type === "gift") {
    const gradId = `ball_${colorName}`;
    const fillVal = document.getElementById(gradId) ? `url(#${gradId})` : colorHex;
    // Коробка
    g.appendChild(svgEl("rect", { x: -11, y: -6, width: 22, height: 17, rx: 2.5, fill: fillVal, stroke: "rgba(0,0,0,0.45)" }));
    // Крышка
    g.appendChild(svgEl("rect", { x: -12.5, y: -10.5, width: 25, height: 6, rx: 2, fill: fillVal, stroke: "rgba(0,0,0,0.45)" }));
    // Золотые ленты и пышный бант
    g.appendChild(svgEl("rect", { x: -2.2, y: -10.5, width: 4.4, height: 21.5, fill: "#fde047" }));
    g.appendChild(svgEl("rect", { x: -11, y: 0, width: 22, height: 3.6, fill: "#fde047" }));
    g.appendChild(svgEl("ellipse", { cx: -4.5, cy: -12.5, rx: 4.5, ry: 2.6, fill: "none", stroke: "#fde047", "stroke-width": 2.2, transform: "rotate(-20 -4.5 -12.5)" }));
    g.appendChild(svgEl("ellipse", { cx: 4.5, cy: -12.5, rx: 4.5, ry: 2.6, fill: "none", stroke: "#fde047", "stroke-width": 2.2, transform: "rotate(20 4.5 -12.5)" }));
  } else if (type === "bell") {
    // Бантик сверху
    g.appendChild(svgEl("circle", { cx: -4, cy: -11, r: 3, fill: "#ef4444" }));
    g.appendChild(svgEl("circle", { cx: 4, cy: -11, r: 3, fill: "#ef4444" }));
    // Купол колокольчика
    g.appendChild(svgEl("path", {
      d: "M -11,7 Q -10,-10 0,-10 Q 10,-10 11,7 Z",
      fill: "url(#ball_gold)",
      stroke: "#92400e",
      "stroke-width": 1,
    }));
    g.appendChild(svgEl("rect", { x: -12, y: 5.5, width: 24, height: 3.5, rx: 1.5, fill: "#fde047", stroke: "#92400e", "stroke-width": 0.8 }));
    g.appendChild(svgEl("circle", { cx: 0, cy: 10.5, r: 3.2, fill: "#b45309" }));
    g.appendChild(svgEl("ellipse", { cx: -3.5, cy: -2, rx: 2, ry: 4.5, fill: "#fef9c3", opacity: 0.65 }));
  } else if (type === "candy") {
    const gradId = `ball_${colorName}`;
    const fillVal = document.getElementById(gradId) ? `url(#${gradId})` : colorHex;
    // Хвостики фантика
    g.appendChild(svgEl("polygon", { points: "-8,0 -17,-7 -15,0 -17,7", fill: fillVal, stroke: "rgba(0,0,0,0.35)" }));
    g.appendChild(svgEl("polygon", { points: "8,0 17,-7 15,0 17,7", fill: fillVal, stroke: "rgba(0,0,0,0.35)" }));
    // Конфета со спиральными полосками
    g.appendChild(svgEl("circle", { cx: 0, cy: 0, r: 9.5, fill: fillVal, stroke: "rgba(255,255,255,0.35)", "stroke-width": 0.8 }));
    g.appendChild(svgEl("path", { d: "M -6,-5 Q 0,0 6,5 M -6,5 Q 0,0 6,-5", stroke: "#ffffff", "stroke-width": 2.2, "stroke-linecap": "round", opacity: 0.85 }));
    g.appendChild(svgEl("circle", { cx: -3, cy: -3.5, r: 2.2, fill: "#ffffff", opacity: 0.65 }));
  }
  return g;
}

function clientToPercent(clientX, clientY) {
  const rect = treeSvg.getBoundingClientRect();
  const x = ((clientX - rect.left) / rect.width) * 100;
  const y = ((clientY - rect.top) / rect.height) * 100;
  return {
    x: Math.round(x * 10) / 10,
    y: Math.round(y * 10) / 10,
  };
}

function renderDecorations() {
  decorLayer.innerHTML = "";
  for (const d of state.decorations) {
    const colorHex = state.ornaments[d.ornament_type]?.colors?.[d.color] || "#e63946";
    const x = (d.x / 100) * 400;
    const y = (d.y / 100) * 500;
    const el = ornamentShape(d.ornament_type, d.color, colorHex, x, y);
    el.dataset.id = d.id;

    el.addEventListener("pointerdown", (e) => {
      e.stopPropagation();
      if (state.myUserId && d.user_id !== state.myUserId) {
        const owner = d.username ? `@${d.username}` : (d.first_name || "Другой игрок");
        toast(`🎄 Эту игрушку повесил(а): ${owner}`);
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
        const rawPt = clientToPercent(e.clientX, e.clientY);
        const clamped = clampToTree(rawPt.x, rawPt.y);
        dragState.curX = clamped.x;
        dragState.curY = clamped.y;
        el.setAttribute("transform", `translate(${(clamped.x / 100) * 400},${(clamped.y / 100) * 500})`);
      }
    });

    el.addEventListener("pointerup", async (e) => {
      if (!dragState || dragState.dec.id !== d.id) return;
      e.stopPropagation();
      suppressNextTreeClick = true;
      setTimeout(() => { suppressNextTreeClick = false; }, 120);
      const finishedDrag = dragState;
      dragState = null;
      if (finishedDrag.moved) {
        spawnParticles(e.clientX, e.clientY, colorHex, 14);
        await saveMoveDecoration(d.id, finishedDrag.curX, finishedDrag.curY);
      } else {
        await onDecorationClick(d);
      }
    });

    decorLayer.appendChild(el);
  }
  $("#counter").textContent = `✨ На ёлке: ${state.decorations.length}`;
}

async function saveMoveDecoration(decorationId, x, y) {
  try {
    const res = await fetch("/api/move", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        decoration_id: decorationId,
        x,
        y,
        init_data: initData,
        user: currentUser,
      }),
    });
    if (!res.ok) throw new Error();
    haptic("light");
    toast("Игрушка перемещена ✨");
    await refreshTreeData();
  } catch {
    toast("Не удалось переместить", true);
    await refreshTreeData();
  }
}

// ============================================================================
// 6. ОТДЕЛЬНАЯ ВКЛАДКА ЛИДЕРБОРДА (ПОДИУМ ТОП-3 + ПОЛНЫЙ СПИСОК ИГРОКОВ)
// ============================================================================
function getDisplayName(row) {
  if (row.username) return `@${row.username}`;
  return row.first_name || `Игрок #${row.user_id}`;
}

function getInitials(row) {
  const name = (row.first_name || row.username || "И").trim();
  return name.slice(0, 1).toUpperCase();
}

function renderLeaderboard() {
  const podiumEl = $("#lbPodium");
  const listEl = $("#leaderboardList");
  if (!podiumEl || !listEl) return;

  let rows = [];
  const mode = state.activeLbTab;
  if (mode === "by_coins") {
    rows = state.leaderboard?.by_coins || [];
  } else if (mode === "chat_stats") {
    rows = state.stats || [];
  } else {
    rows = state.leaderboard?.by_toys || [];
  }

  podiumEl.innerHTML = "";
  listEl.innerHTML = "";

  if (!rows.length) {
    listEl.innerHTML = `<li class="lb-row"><span>Пока нет участников</span><span>—</span></li>`;
    return;
  }

  // Подиум Топ-3 (порядок отображения: 2 место слева, 1 место в центре, 3 место справа)
  const top3Order = [rows[1], rows[0], rows[2]];
  const ranks = [2, 1, 3];
  const medals = { 1: "🥇", 2: "🥈", 3: "🥉" };

  top3Order.forEach((item, idx) => {
    const r = ranks[idx];
    const card = document.createElement("div");
    card.className = `podium-card rank-${r}`;
    if (!item) {
      card.innerHTML = `
        <div class="podium-medal">${medals[r]}</div>
        <div class="podium-avatar">—</div>
        <div class="podium-name">Свободно</div>
        <div class="podium-score">0</div>
      `;
    } else {
      const scoreText = mode === "by_coins"
        ? `${item.coins ?? 0} 🪙`
        : `${item.count ?? 0} 🎄`;
      card.innerHTML = `
        <div class="podium-medal">${medals[r]}</div>
        <div class="podium-avatar">${escapeHtml(getInitials(item))}</div>
        <div class="podium-name">${escapeHtml(getDisplayName(item))}</div>
        <div class="podium-score">${scoreText}</div>
      `;
    }
    podiumEl.appendChild(card);
  });

  // Полный список всех игроков
  rows.forEach((row, idx) => {
    const isMe = Number(row.user_id) === Number(state.myUserId);
    const li = document.createElement("li");
    li.className = "lb-row" + (isMe ? " is-me" : "");
    const medal = ["🥇", "🥈", "🥉"][idx] || `${idx + 1}.`;
    const mainMetric = mode === "by_coins"
      ? `${row.coins ?? 0} 🪙`
      : `${row.count ?? 0} 🎄`;
    const subMetric = mode === "by_coins"
      ? `Наряжено игрушек: ${row.count ?? 0} 🎄`
      : `Баланс: ${row.coins ?? 0} 🪙`;

    li.innerHTML = `
      <div class="lb-left">
        <span class="lb-rank">${medal}</span>
        <div class="lb-avatar">${escapeHtml(getInitials(row))}</div>
        <div class="lb-user-meta">
          <div class="lb-uname">${escapeHtml(getDisplayName(row))} ${isMe ? "<b>(Вы)</b>" : ""}</div>
          <div class="lb-sub">${subMetric}</div>
        </div>
      </div>
      <div class="lb-right">
        <div class="lb-main-val">${mainMetric}</div>
      </div>
    `;
    listEl.appendChild(li);
  });
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

// ============================================================================
// 7. ИНВЕНТАРЬ, МАГАЗИН И ДОНАТ
// ============================================================================
function renderPalette() {
  palette.innerHTML = "";
  for (const [type, info] of Object.entries(state.ornaments)) {
    const qty = Number(state.inventory?.[type] || 0);
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "ornament-btn" + (type === state.selectedType ? " selected" : "");
    btn.innerHTML = `
      <span class="qty-badge ${qty === 0 ? "empty" : ""}">x${qty}</span>
      <span class="emoji">${info.emoji}</span>
      <span class="name">${info.name}</span>
    `;
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
  const info = state.ornaments[state.selectedType];
  if (info) {
    for (const [cname, hex] of Object.entries(info.colors)) {
      const dot = document.createElement("button");
      dot.type = "button";
      dot.className = "color-dot" + (cname === state.selectedColor ? " selected" : "");
      dot.style.background = hex;
      dot.title = cname;
      dot.onclick = () => {
        state.selectedColor = cname;
        haptic("light");
        renderPalette();
      };
      colorsDiv.appendChild(dot);
    }
  }
  palette.appendChild(colorsDiv);
}

function renderShop() {
  const grid = $("#shopGrid");
  if (!grid) return;
  grid.innerHTML = "";
  for (const [type, info] of Object.entries(state.ornaments)) {
    const qty = Number(state.inventory?.[type] || 0);
    const card = document.createElement("div");
    card.className = "shop-item-card";
    card.innerHTML = `
      <div class="s-emoji">${info.emoji}</div>
      <div class="s-title">${info.name}</div>
      <div class="s-owned">В инвентаре: <b>${qty} шт.</b></div>
      <button type="button" class="buy-coin-btn" data-type="${type}">
        Купить за ${info.price} 🪙
      </button>
    `;
    card.querySelector(".buy-coin-btn").addEventListener("click", (ev) => {
      buyOrnamentWithCoins(type, ev.clientX, ev.clientY);
    });
    grid.appendChild(card);
  }
}

function renderDonateShop() {
  const list = $("#donateList");
  if (!list) return;
  list.innerHTML = "";
  for (const [packId, pack] of Object.entries(state.donatePacks)) {
    const card = document.createElement("div");
    card.className = "donate-card";
    card.innerHTML = `
      <div class="donate-top">
        <div class="donate-emoji">${pack.emoji}</div>
        <div class="donate-info">
          <h3>${escapeHtml(pack.title)}</h3>
          <p>${escapeHtml(pack.description)}</p>
        </div>
      </div>
      <div class="donate-btns">
        <button type="button" class="pay-stars-btn" data-pack="${packId}">
          ⭐️ ${pack.stars_price} Stars
        </button>
        <button type="button" class="pay-gram-btn" data-pack="${packId}">
          💎 ${pack.gram_price} GRAM
        </button>
      </div>
    `;
    card.querySelector(".pay-stars-btn").addEventListener("click", () => buyWithStars(packId));
    card.querySelector(".pay-gram-btn").addEventListener("click", () => openGramModal(packId));
    list.appendChild(card);
  }
}

async function buyOrnamentWithCoins(ornamentType, clientX, clientY) {
  await flushPendingClicks();
  try {
    const res = await fetch("/api/buy", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ornament_type: ornamentType,
        count: 1,
        init_data: initData,
        user: currentUser,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Не удалось купить");
    haptic("medium");
    if (clientX && clientY) spawnParticles(clientX, clientY, "#22c55e", 20);
    applyProfile(data.profile);
    state.selectedType = ornamentType;
    state.selectedColor = Object.keys(state.ornaments[ornamentType].colors)[0];
    renderPalette();
    toast(data.message || "Игрушка куплена! 🎉");
  } catch (err) {
    toast(err.message || "Не хватает монет", true);
  }
}

async function buyWithStars(packId) {
  try {
    const res = await fetch("/api/donate/stars-invoice", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pack_id: packId,
        currency: "XTR",
        init_data: initData,
        user: currentUser,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Ошибка создания счёта");

    if (data.invoice_link && tg?.openInvoice) {
      tg.openInvoice(data.invoice_link, async (status) => {
        if (status === "paid") {
          await claimDonateReward(packId, "XTR", data.order_id);
        } else if (status === "cancelled") {
          toast("Оплата отменена", true);
        }
      });
    } else if (data.invoice_link) {
      window.open(data.invoice_link, "_blank");
    } else {
      toast("Счёт Stars доступен внутри Telegram", true);
    }
  } catch (err) {
    toast(err.message || "Ошибка оплаты Stars", true);
  }
}

function openGramModal(packId) {
  const pack = state.donatePacks[packId];
  if (!pack) return;
  state.activeGramPack = pack;
  const memo = `NYTREE_${currentUser.id}_${packId}`;
  $("#gramModalTitle").textContent = `💎 ${pack.title}`;
  $("#gramPackDesc").textContent = pack.description;
  $("#gramAmountText").textContent = `${pack.gram_price} GRAM`;
  $("#gramWalletCode").textContent = state.gramWallet || "UQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAJKZ";
  $("#gramMemoCode").textContent = memo;
  const wallet = encodeURIComponent(state.gramWallet || "");
  $("#gramDeepLink").href = `https://app.tonkeeper.com/transfer/${wallet}?text=${encodeURIComponent(memo)}`;
  $("#gramModal").classList.remove("hidden");
}

async function claimDonateReward(packId, currency, orderId = 0) {
  try {
    const res = await fetch("/api/donate/claim", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pack_id: packId,
        currency,
        order_id: orderId,
        init_data: initData,
        user: currentUser,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Ошибка начисления");
    haptic("heavy");
    spawnParticles(window.innerWidth / 2, window.innerHeight / 2, "#fde047", 32);
    applyProfile(data.profile);
    $("#gramModal").classList.add("hidden");
    toast(data.message || "Набор получен! 🎉");
  } catch (err) {
    toast(err.message || "Ошибка начисления", true);
  }
}

$("#copyWalletBtn").addEventListener("click", () => {
  navigator.clipboard?.writeText($("#gramWalletCode").textContent || "");
  toast("Адрес кошелька скопирован 📋");
});

$("#confirmGramPaidBtn").addEventListener("click", async () => {
  if (!state.activeGramPack) return;
  await claimDonateReward(state.activeGramPack.id, "GRAM", 0);
});

$("#closeGramModalBtn").addEventListener("click", () => {
  $("#gramModal").classList.add("hidden");
});

// ============================================================================
// 8. КЛИКЕР С КОМБО И ЧАСТИЦАМИ
// ============================================================================
const bigClickBtn = $("#bigClickBtn");
const clickerStage = $("#clickerStage");

bigClickBtn.addEventListener("pointerdown", (e) => {
  e.preventDefault();
  if (state.energy <= 0) {
    toast("Энергия закончилась! Подожди пару секунд ⚡", true);
    return;
  }
  const now = Date.now();
  if (now - state.lastClickAt < 700) {
    state.combo = Math.min(5, state.combo + 1);
  } else {
    state.combo = 1;
  }
  state.lastClickAt = now;
  $("#comboBadge").textContent = `🔥 Комбо x${state.combo}`;

  state.energy = Math.max(0, state.energy - 1);
  state.coins += state.clickPower;
  state.pendingClicks += 1;
  haptic("light");
  updateHeaderAndClickerUI();
  saveBackup();

  const rect = clickerStage.getBoundingClientRect();
  const cx = e.clientX || rect.left + rect.width / 2;
  const cy = e.clientY || rect.top + rect.height / 2;
  spawnParticles(cx, cy, "#fde047", 10);

  const fx = (e.clientX ? e.clientX - rect.left : rect.width / 2) + (Math.random() * 34 - 17);
  const fy = (e.clientY ? e.clientY - rect.top : rect.height / 2) - 12;
  const plus = document.createElement("div");
  plus.className = "float-plus";
  plus.textContent = `+${state.clickPower} 🪙`;
  plus.style.left = `${fx}px`;
  plus.style.top = `${fy}px`;
  clickerStage.appendChild(plus);
  setTimeout(() => plus.remove(), 750);

  clearTimeout(clickFlushTimer);
  clickFlushTimer = setTimeout(flushPendingClicks, 550);
});

async function flushPendingClicks() {
  if (state.pendingClicks <= 0) return;
  const toSend = state.pendingClicks;
  state.pendingClicks = 0;
  try {
    const res = await fetch("/api/click", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        clicks: toSend,
        init_data: initData,
        user: currentUser,
      }),
    });
    if (res.ok) {
      const data = await res.json();
      if (state.pendingClicks === 0 && data.profile) {
        applyProfile(data.profile);
      }
    }
  } catch (e) {}
}

$("#upgradeClickBtn").addEventListener("click", async (ev) => {
  await flushPendingClicks();
  try {
    const res = await fetch("/api/upgrade-click", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        init_data: initData,
        user: currentUser,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Недостаточно монет");
    haptic("medium");
    spawnParticles(ev.clientX || window.innerWidth / 2, ev.clientY || window.innerHeight / 2, "#38bdf8", 24);
    applyProfile(data.profile);
    toast(data.message || "Сила клика увеличена! ⚡");
  } catch (err) {
    toast(err.message || "Не хватает монет", true);
  }
});

setInterval(() => {
  if (state.energy < state.maxEnergy) {
    state.energy = Math.min(state.maxEnergy, state.energy + 3);
    updateHeaderAndClickerUI();
  }
}, 1000);

// ============================================================================
// 9. ЗАГРУЗКА ЁЛКИ, УКРАШЕНИЕ И СИНХРОНИЗАЦИЯ
// ============================================================================
async function refreshTreeData() {
  const q = new URLSearchParams({
    user_id: String(currentUser.id),
    username: currentUser.username || "",
    first_name: currentUser.first_name || "Игрок",
    t: String(Date.now()),
  });
  const res = await fetch(`/api/tree/${chatId}?${q.toString()}`, { cache: "no-store" });
  if (!res.ok) throw new Error(await res.text());
  const data = await res.json();
  state.ornaments = data.ornaments;
  state.donatePacks = data.donate_packs || {};
  state.gramWallet = data.gram_wallet || "";
  state.decorations = data.decorations || [];
  state.stats = data.stats || [];
  if (data.leaderboard) {
    state.leaderboard = data.leaderboard;
  }
  if (data.profile) {
    state.coins = Number(data.profile.coins ?? state.coins);
    state.clickPower = Number(data.profile.click_power ?? state.clickPower);
    state.inventory = data.profile.inventory || state.inventory;
  }
  $("#chatTitle").textContent = data.tree.chat_title ? `${data.tree.chat_title}` : "Общая новогодняя ёлка";
  if (data.tree.is_finished) {
    $("#hint").textContent = "🎉 Ивент завершён! С Новым годом!";
  }
  updateHeaderAndClickerUI();
  renderPalette();
  renderShop();
  renderDonateShop();
  renderDecorations();
  renderLeaderboard();
  saveBackup();
}

async function initLoadAndSync() {
  try {
    await refreshTreeData();
    const backup = loadLocalBackup();
    if (backup) {
      const myServerDecs = state.decorations.filter((d) => d.user_id === state.myUserId);
      const needSync =
        (backup.coins && backup.coins > state.coins) ||
        (backup.click_power && backup.click_power > state.clickPower) ||
        (myServerDecs.length === 0 && Array.isArray(backup.decorations) && backup.decorations.length > 0);
      if (needSync) {
        const syncRes = await fetch("/api/sync", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            chat_id: Number(chatId),
            coins: backup.coins,
            click_power: backup.click_power,
            inventory: backup.inventory,
            decorations: backup.decorations,
            init_data: initData,
            user: currentUser,
          }),
        });
        if (syncRes.ok) {
          await refreshTreeData();
        }
      }
    }
  } catch (e) {
    $("#chatTitle").textContent = "Не удалось загрузить ёлку 😢";
    toast("Ошибка загрузки", true);
  }
}

async function onDecorationClick(d) {
  if (state.myUserId && d.user_id !== state.myUserId) {
    const owner = d.username ? `@${d.username}` : (d.first_name || "Другой игрок");
    toast(`🎄 Эту игрушку повесил(а): ${owner}`);
    return;
  }
  if (!confirm("Снять эту игрушку с ёлки обратно в инвентарь?")) return;
  try {
    const res = await fetch("/api/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        decoration_id: d.id,
        init_data: initData,
        user: currentUser,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Ошибка");
    toast("Игрушка возвращена в инвентарь 🎒");
    haptic("medium");
    if (data.profile) applyProfile(data.profile);
    await refreshTreeData();
  } catch {
    toast("Не удалось снять", true);
  }
}

treeSvg.addEventListener("click", async (e) => {
  if (suppressNextTreeClick) return;
  if (e.target.closest(".dec-item")) return;

  const pt = clientToPercent(e.clientX, e.clientY);
  // Проверяем, что нажатие попало именно на крону ёлки, а не в небо или сугробы!
  if (!isPointInsideTree(pt.x, pt.y)) {
    haptic("light");
    spawnParticles(e.clientX, e.clientY, "#94a3b8", 6);
    toast("Вешай игрушки прямо на веточки ёлки! 🎄", true);
    return;
  }

  const qty = Number(state.inventory?.[state.selectedType] || 0);
  if (qty <= 0) {
    const info = state.ornaments[state.selectedType];
    toast(`Нет «${info?.name || "игрушки"}» в инвентаре! Купи в Магазине 🛍`, true);
    return;
  }

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
        user: currentUser,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Ошибка");
    }
    const colorHex = state.ornaments[state.selectedType]?.colors?.[state.selectedColor] || "#fde047";
    spawnParticles(e.clientX, e.clientY, colorHex, 26);
    haptic("medium");
    toast("Игрушка повешена на ёлку! ✨");
    if (data.profile) applyProfile(data.profile);
    await refreshTreeData();
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

drawSnowAndStars();
drawGarlandLights();
drawTopStar();
updateCountdown();
setInterval(updateCountdown, 30000);
// Периодическое обновление ёлки и лидерборда, чтобы видеть действия других игроков в реальном времени
setInterval(() => {
  refreshTreeData().catch(() => {});
}, 12000);
initLoadAndSync();
