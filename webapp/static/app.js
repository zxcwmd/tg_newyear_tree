const tg = window.Telegram?.WebApp;
if (tg) {
  tg.ready();
  tg.expand();
}

const params = new URLSearchParams(window.location.search);
const rawUrlChat = params.get("chat_id") || params.get("startapp") || tg?.initDataUnsafe?.start_param || "";
const urlInviteCode =
  params.get("invite") ||
  (String(rawUrlChat).startsWith("team_") ? String(rawUrlChat) : "") ||
  (String(tg?.initDataUnsafe?.start_param || params.get("startapp") || "").startsWith("team_")
    ? String(tg?.initDataUnsafe?.start_param || params.get("startapp") || "")
    : "");
// Рефералка: ?ref=12345 или /start ref_12345
let urlReferrerId = Number(params.get("ref") || params.get("referrer_id") || 0);
if (!urlReferrerId) {
  const sp = String(tg?.initDataUnsafe?.start_param || params.get("startapp") || "");
  if (sp.startsWith("ref_")) {
    const n = Number(sp.slice(4));
    if (!Number.isNaN(n) && n > 0) urlReferrerId = n;
  }
}
// (проверка «не сам на себя» — после определения currentUser ниже)

// Личная ёлка игрока: id вида -(PERSONAL_TREE_BASE + user_id) приходит с сервера.
// До первой загрузки используем виртуальный "personal" и открываем личную ёлку.
const PERSONAL_TREE_BASE = 4000000000000000;

function normalizeChatId(val) {
  const n = Number(val);
  if (!Number.isNaN(n) && n < 0) return String(n);
  return "personal";
}

function personalTreeIdLocal() {
  if (state && state.personalTreeId) return String(state.personalTreeId);
  const uid = Number(currentUser?.id || tg?.initDataUnsafe?.user?.id || 1);
  return String(-(PERSONAL_TREE_BASE + uid));
}

// chat_id для запросов: "personal" превращается в реальный id личной ёлки
function requestChatId() {
  return String(chatId) === "personal" ? personalTreeIdLocal() : String(chatId);
}

let chatId = normalizeChatId(rawUrlChat);
if (String(chatId) === "personal") chatId = "personal";
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
if (urlReferrerId && urlReferrerId === Number(currentUser.id)) urlReferrerId = 0;
const BACKUP_KEY = `ny_backup_v8_${currentUser.id}`;

let state = {
  tree: null,
  ornaments: {},
  donatePacks: {},
  botUsername: "",
  webappUrl: window.location.origin,
  selectedType: "ball",
  selectedColor: "red",
  decorations: [],
  stats: [],
  leaderboard: { by_toys: [], by_turnover: [], team_trees: [] },
  teamTrees: [],
  activeLbTab: "by_toys",
  activeSegment: "all",
  myUserId: currentUser.id,
  coins: 50,
  coinTurnover: 50,
  clickPower: 1,
  inventory: { ball: 2, snowflake: 1 },
  energy: 500,
  maxEnergy: 500,
  pendingClicks: 0,
  combo: 1,
  lastClickAt: 0,
  activeGramOrder: null,
  treeThemes: null,
  lootboxPrice: 100,
  lootboxPool: [],
  nftCatalog: [],
  nftGifts: [],
  nftDraftToken: 0,
  nftDraftTo: 0,
  nftMintEnabled: false,
  adventRewards: [],
  dailyStreak: 0,
  canClaimDaily: true,
  referralsCount: 0,
  styleDraft: { bg_theme: "aurora", garland_style: "classic", topper_type: "star" },
  activeOrnament: null,
  isPersonalTree: true,
  members: [],
  membersCount: 1,
  teamTree: null,
  personalTreeId: 0,
  crowdAnimated: false,
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
  toast._timer = setTimeout(() => t.classList.remove("show"), 2400);
}

function haptic(type = "light") {
  try { tg?.HapticFeedback?.impactOccurred(type); } catch (e) {}
}

// ============================================================================
// 1. ВЫБОР СЕГМЕНТА (ЯРУСА) ЁЛКИ — ПЛАВНЫЙ ЗУМ КАМЕРЫ
// ============================================================================
const SEGMENTS_VB = {
  all: { x: 0, y: 0, w: 400, h: 500 },
  top: { x: 92, y: 22, w: 216, h: 205 },
  mid: { x: 64, y: 132, w: 272, h: 205 },
  bot: { x: 42, y: 226, w: 316, h: 245 },
};

let currentVB = { ...SEGMENTS_VB.all };
let vbAnimFrame = null;

function setTreeSegment(segKey) {
  const target = SEGMENTS_VB[segKey] || SEGMENTS_VB.all;
  state.activeSegment = segKey;
  $$(".seg-btn").forEach((b) => b.classList.toggle("active", b.dataset.seg === segKey));
  haptic("light");

  if (vbAnimFrame) cancelAnimationFrame(vbAnimFrame);
  const startVB = { ...currentVB };
  const startTime = performance.now();
  const duration = 260;

  function step(now) {
    const t = Math.min(1, (now - startTime) / duration);
    const ease = 1 - Math.pow(1 - t, 3);
    currentVB.x = startVB.x + (target.x - startVB.x) * ease;
    currentVB.y = startVB.y + (target.y - startVB.y) * ease;
    currentVB.w = startVB.w + (target.w - startVB.w) * ease;
    currentVB.h = startVB.h + (target.h - startVB.h) * ease;
    treeSvg.setAttribute(
      "viewBox",
      `${currentVB.x.toFixed(1)} ${currentVB.y.toFixed(1)} ${currentVB.w.toFixed(1)} ${currentVB.h.toFixed(1)}`
    );
    if (t < 1) {
      vbAnimFrame = requestAnimationFrame(step);
    }
  }
  vbAnimFrame = requestAnimationFrame(step);
}

$$(".seg-btn").forEach((btn) => {
  btn.addEventListener("click", () => setTreeSegment(btn.dataset.seg));
});

// ============================================================================
// 2. ЖИВОЙ ФОН (#bgCanvas) И СИСТЕМА ЧАСТИЦ (#fxCanvas)
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

  fxCtx.clearRect(0, 0, bgW, bgH);
  for (let i = fxParticles.length - 1; i >= 0; i--) {
    const p = fxParticles[i];
    p.x += p.vx;
    p.y += p.vy;
    p.vy += 0.14;
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
// 3. ПРОВЕРКА ГРАНИЦ ЁЛКИ И КОНВЕРТАЦИЯ КООРДИНАТ С УЧЁТОМ ЗУМА СЕГМЕНТА
// ============================================================================
const TREE_TIERS = [
  [60.0, 216.0, 8.0, 76.0],
  [146.0, 326.0, 14.0, 96.0],
  [236.0, 430.0, 18.0, 120.0],
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
  const sy = Math.max(64.0, Math.min(426.0, yPct * 5.0));
  let allowedHw = 20.0;
  for (const [yTop, yBot, hwTop, hwBot] of TREE_TIERS) {
    if (sy >= yTop && sy <= yBot) {
      const t = (sy - yTop) / (yBot - yTop);
      const hw = hwTop + t * (hwBot - hwTop) - 2.0;
      if (hw > allowedHw) allowedHw = hw;
    }
  }
  const clampedSx = Math.max(200.0 - allowedHw, Math.min(200.0 + allowedHw, sx));
  return {
    x: Math.round((clampedSx / 4.0) * 10) / 10,
    y: Math.round((sy / 5.0) * 10) / 10,
  };
}

function clientToPercent(clientX, clientY) {
  const rect = treeSvg.getBoundingClientRect();
  const relX = (clientX - rect.left) / rect.width;
  const relY = (clientY - rect.top) / rect.height;
  // Переводим с учётом текущего приближенного сегмента (currentVB) в глобальные координаты SVG (0..400, 0..500)
  const svgX = currentVB.x + relX * currentVB.w;
  const svgY = currentVB.y + relY * currentVB.h;
  return {
    x: Math.round((svgX / 400.0) * 1000) / 10,
    y: Math.round((svgY / 500.0) * 1000) / 10,
  };
}

// ============================================================================
// 4. ЛОКАЛЬНЫЙ И ОБЛАЧНЫЙ БЭКАП ПРОГРЕССА
// ============================================================================
function saveBackup() {
  const myDecs = state.decorations.filter((d) => d.user_id === state.myUserId);
  const payload = {
    coins: state.coins,
    coin_turnover: state.coinTurnover,
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
    // Миграция со старых ключей v6/v7
    for (const oldKey of [`ny_backup_v7_${currentUser.id}`, `ny_backup_v6_${currentUser.id}`]) {
      const oldRaw = localStorage.getItem(oldKey);
      if (oldRaw) return JSON.parse(oldRaw);
    }
  } catch (e) {}
  return null;
}

// ============================================================================
// 5. НАВИГАЦИЯ ПО ВКЛАДКАМ
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
    const res = await fetch(`/api/leaderboard?chat_id=${requestChatId()}&user_id=${currentUser.id}&t=${Date.now()}`, { cache: "no-store" });
    if (!res.ok) return;
    const data = await res.json();
    state.stats = data.chat_stats || state.stats;
    state.leaderboard = {
      by_toys: data.by_toys || [],
      by_turnover: data.by_turnover || [],
      team_trees: data.team_trees || [],
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
  state.coinTurnover = Number(profile.coin_turnover ?? Math.max(state.coinTurnover, state.coins));
  state.clickPower = Number(profile.click_power ?? state.clickPower);
  state.dailyStreak = Number(profile.daily_streak ?? state.dailyStreak ?? 0);
  state.canClaimDaily = profile.can_claim_daily !== false;
  state.referralsCount = Number(profile.referrals_count ?? state.referralsCount ?? 0);
  if (profile.inventory) {
    state.inventory = { ...state.inventory, ...profile.inventory };
  }
  if (Array.isArray(profile.team_trees)) {
    state.teamTrees = profile.team_trees;
    renderTreeSwitcher();
  }
  updateHeaderAndClickerUI();
  updateDailyUI();
  renderPalette();
  renderShop();
  saveBackup();
}

function updateDailyUI() {
  const badge = $("#dailyStreakBadge");
  if (badge) badge.textContent = `Серия: ${state.dailyStreak} дн.`;
  const btn = $("#dailyGiftBtn");
  if (btn) btn.classList.toggle("ready", !!state.canClaimDaily);
  const lbl = $("#referralCountLabel");
  if (lbl) lbl.textContent = `Приглашено друзей: ${state.referralsCount}`;
}

function updateHeaderAndClickerUI() {
  $("#coinBalance").textContent = state.coins;
  $("#turnoverChip").textContent = `🔄 Оборот: ${state.coinTurnover} 🪙`;
  $("#clickerCoins").textContent = `${state.coins} / ${state.coinTurnover} 🪙`;
  $("#clickPowerLabel").textContent = `+${state.clickPower} 🪙`;
  $("#upgradeCost").textContent = state.clickPower * 100;
  $("#energyText").textContent = `${state.energy} / ${state.maxEnergy}`;
  const pct = Math.max(0, Math.min(100, (state.energy / state.maxEnergy) * 100));
  $("#energyBarFill").style.width = `${pct}%`;
}

// ============================================================================
// 6. ЛИЧНАЯ ЁЛКА И КОМАНДА ПО ССЫЛКЕ ОТ БОТА
// ============================================================================
function getInviteLinkForTree(treeObj) {
  if (!treeObj) return window.location.origin;
  const code = treeObj.invite_code || `team_${treeObj.chat_id}`;
  if (state.botUsername) {
    return `https://t.me/${state.botUsername}?start=${code}`;
  }
  return `${window.location.origin}/?invite=${code}`;
}

function renderTreeSwitcher() {
  const sel = $("#treeSwitcher");
  if (!sel) return;
  sel.innerHTML = "";

  const personalOpt = document.createElement("option");
  personalOpt.value = personalTreeIdLocal();
  personalOpt.textContent = "🎄 Моя ёлка";
  sel.appendChild(personalOpt);

  const teams = [...(state.teamTrees || [])];
  if (state.teamTree && !teams.some((t) => String(t.chat_id) === String(state.teamTree.chat_id))) {
    teams.unshift(state.teamTree);
  }
  if (state.tree && Number(state.tree.chat_id) < 0 && !teams.some((t) => String(t.chat_id) === String(state.tree.chat_id))) {
    teams.unshift(state.tree);
  }
  const seen = new Set([personalTreeIdLocal()]);
  for (const t of teams) {
    const cidStr = String(t.chat_id);
    if (seen.has(cidStr)) continue;
    seen.add(cidStr);
    const teamOpt = document.createElement("option");
    teamOpt.value = cidStr;
    teamOpt.textContent = `👥 ${t.chat_title || "Командная ёлка"}`;
    sel.appendChild(teamOpt);
  }

  const currentVal = String(chatId);
  const values = [...sel.options].map((o) => o.value);
  sel.value = values.includes(currentVal) ? currentVal : values[0];

  // Панель команды под переключателем
  const shareRow = $("#teamShareRow");
  const isTeam = !state.isPersonalTree && Number(chatId) < 0;
  if (shareRow) shareRow.classList.toggle("hidden", !isTeam);
  if (isTeam && state.tree) {
    const code = state.tree.invite_code || `team_${state.tree.chat_id}`;
    $("#teamCodeLabel").textContent = `👥 Участников: ${state.membersCount}`;
    const link = getInviteLinkForTree(state.tree);
    const codeEl = $("#teamCodeLabel");
    if (codeEl) codeEl.dataset.code = code;
    if (codeEl) codeEl.dataset.link = link;
  }
  const btn = $("#inviteTeamBtn");
  if (btn) btn.textContent = state.teamTree ? "👥 Пригласить друга" : "👥 Позвать друзей";
}

function renderCrowd() {
  const row = $("#crowdRow");
  if (!row) return;
  row.innerHTML = "";
  const count = Math.max(0, Number(state.membersCount || 0));
  const members = Array.isArray(state.members) ? state.members : [];
  const isTeam = !state.isPersonalTree;

  const shown = Math.min(count, 13);
  for (let i = 0; i < shown; i++) {
    const m = members[i] || {};
    const isMe = Number(m.user_id) === Number(state.myUserId);
    const figure = document.createElement("div");
    figure.className = "crowd-figure" + (isMe ? " is-me" : "");
    figure.style.animationDelay = `${(i * 0.08).toFixed(2)}s`;
    const hatHue = Number(m.user_id || i * 37) % 360;
    figure.innerHTML = `
      <div class="crowd-person hat-hue-${(Number(m.user_id || 0) % 6 + 6) % 6}">
        <div class="person-hat"></div>
        <div class="person-head"></div>
        <div class="person-body"></div>
      </div>
      <div class="crowd-name">${escapeHtml((m.first_name || (isMe ? "Ты" : "Друг")).slice(0, 10))}</div>
    `;
    row.appendChild(figure);
  }
  if (count > shown) {
    const more = document.createElement("div");
    more.className = "crowd-figure crowd-more";
    more.innerHTML = `<div class="crowd-badge">+${count - shown}</div>`;
    row.appendChild(more);
  }

  $("#crowdTitle").textContent = isTeam
    ? `👥 Ёлку собирают: ${count} ${count === 1 ? "человек" : "чел."}`
    : "🎄 Наряжаешь один";
  $("#crowdHint").textContent = isTeam
    ? (count > 1
        ? "Это ваша общая ёлка: игрушки и монеты у каждого свои, а ёлка одна на всех 🎁"
        : "Пока в команде только ты. Нажми «Пригласить друга» — бот сгенерирует ссылку 🎄")
    : "Пока ты играешь один — ёлка только твоя. Позови друга, и появятся человечки в шапочках 👇";
  const inviteBtn = $("#crowdInviteBtn");
  if (inviteBtn) inviteBtn.textContent = state.teamTree ? "+ Пригласить друга" : "+ Позвать друзей";
}

function switchChat(newChatId) {
  chatId = String(newChatId);
  haptic("light");
  return refreshTreeData();
}

$("#treeSwitcher").addEventListener("change", (e) => {
  switchChat(e.target.value).catch(() => toast("Не удалось открыть ёлку", true));
});

function openTeamModal() {
  $("#createdInviteBox").classList.add("hidden");
  const label = $("#teamMembersLabel");
  const ownCount = state.isPersonalTree ? 1 : Math.max(1, Number(state.membersCount || 1));
  if (label) label.textContent = `Участников: ${ownCount}`;
  $("#teamModal").classList.remove("hidden");
}

$("#inviteTeamBtn").addEventListener("click", openTeamModal);
$("#crowdInviteBtn").addEventListener("click", openTeamModal);

$("#closeTeamModalBtn").addEventListener("click", () => {
  $("#teamModal").classList.add("hidden");
});
$("#teamModal").addEventListener("click", (e) => {
  if (e.target === $("#teamModal")) $("#teamModal").classList.add("hidden");
});

$("#createTeamBtn").addEventListener("click", async () => {
  try {
    const res = await fetch("/api/team/create", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "", init_data: initData, user: currentUser }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Ошибка создания");
    haptic("heavy");
    state.teamTree = data.tree;
    if (data.profile) applyProfile(data.profile);
    $("#teamInviteLinkCode").textContent = data.bot_invite_url || getInviteLinkForTree(data.tree);
    $("#createdInviteBox").classList.remove("hidden");
    const label = $("#teamMembersLabel");
    if (label) label.textContent = `Участников: ${Math.max(1, Number(data.members_count || 1))}`;
    await switchChat(data.tree_id || data.tree.chat_id);
    toast("Ссылка-приглашение готова! Отправь её другу 🎄");
  } catch (err) {
    toast(err.message || "Не удалось создать команду", true);
  }
});

function extractInviteCode(raw) {
  let code = String(raw || "").trim();
  if (code.includes("start=")) code = code.split("start=")[1];
  if (code.includes("invite=")) code = code.split("invite=")[1];
  return code.split("&")[0].split("?")[0].trim();
}

$("#joinTeamBtn").addEventListener("click", async () => {
  const code = extractInviteCode($("#joinCodeInput").value || "");
  if (!code) {
    toast("Вставь ссылку-приглашение или код", true);
    return;
  }
  try {
    const res = await fetch("/api/team/join", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ invite_code: code, init_data: initData, user: currentUser }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Ёлка не найдена");
    haptic("medium");
    state.teamTree = data.tree;
    if (data.profile) applyProfile(data.profile);
    $("#teamModal").classList.add("hidden");
    $("#joinCodeInput").value = "";
    await switchChat(data.tree_id || data.tree.chat_id);
    toast(`Ты в команде «${data.tree.chat_title}»! 👥`);
  } catch (err) {
    toast(err.message || "Ссылка не найдена", true);
  }
});

function shareCurrentTeamTree(inviteUrl, treeTitle) {
  const text = `🎄 Заходи наряжать нашу общую новогоднюю ёлку «${treeTitle || "Друзья"}»! Жми на ссылку — бот всё откроет сам.`;
  const shareLink = `https://t.me/share/url?url=${encodeURIComponent(inviteUrl)}&text=${encodeURIComponent(text)}`;
  if (tg?.openTelegramLink) {
    tg.openTelegramLink(shareLink);
  } else {
    window.open(shareLink, "_blank");
  }
}

$("#copyTeamLinkBtn").addEventListener("click", () => {
  const link = $("#teamInviteLinkCode").textContent || getInviteLinkForTree(state.tree);
  navigator.clipboard?.writeText(link);
  toast("Ссылка-приглашение скопирована! 📋");
});

$("#tgShareTeamBtn").addEventListener("click", () => {
  const link = $("#teamInviteLinkCode").textContent || getInviteLinkForTree(state.tree);
  shareCurrentTeamTree(link, state.tree?.chat_title);
});

$("#shareTeamBtn").addEventListener("click", async () => {
  const link = ($("#teamCodeLabel")?.dataset?.link) || getInviteLinkForTree(state.tree);
  try {
    await navigator.clipboard.writeText(link);
    toast("Ссылка скопирована! Отправь её другу 🎄");
  } catch (e) {
    toast(link);
  }
});

$("#joinByCodeBtn").addEventListener("click", () => openTeamModal());

// ============================================================================
// 7. ОТРИСОВКА ЁЛКИ, ГИРЛЯНДЫ И ИГРУШЕК
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

function getGarlandColors() {
  const styleKey = state.tree?.garland_style || "classic";
  const theme = state.treeThemes?.garlands?.[styleKey];
  if (theme && Array.isArray(theme.colors) && theme.colors.length) return theme.colors;
  return ["#fde047", "#f43f5e", "#38bdf8", "#34d399", "#c084fc"];
}

function drawGarlandLights() {
  const g = $("#garlandLights");
  g.innerHTML = "";
  const colors = getGarlandColors();
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
  const topper = state.tree?.topper_type || "star";
  g.appendChild(svgEl("circle", { cx: 200, cy: 48, r: 28, fill: "#fde047", opacity: 0.22, filter: "url(#glowFilter)" }));
  if (topper === "crown") {
    g.appendChild(svgEl("path", {
      d: "M 178,58 L 176,34 L 190,46 L 200,28 L 210,46 L 224,34 L 222,58 Z",
      fill: "#facc15", stroke: "#92400e", "stroke-width": 1.5, "stroke-linejoin": "round",
    }));
    g.appendChild(svgEl("circle", { cx: 200, cy: 50, r: 4, fill: "#ef4444" }));
    g.appendChild(svgEl("circle", { cx: 186, cy: 52, r: 3, fill: "#38bdf8" }));
    g.appendChild(svgEl("circle", { cx: 214, cy: 52, r: 3, fill: "#34d399" }));
  } else if (topper === "angel") {
    g.appendChild(svgEl("circle", { cx: 200, cy: 40, r: 9, fill: "#fde68a", stroke: "#92400e", "stroke-width": 1.2 }));
    g.appendChild(svgEl("path", { d: "M 186,52 Q 200,44 214,52 L 210,68 Q 200,62 190,68 Z", fill: "#ffffff", stroke: "#cbd5e1", "stroke-width": 1.2 }));
    g.appendChild(svgEl("ellipse", { cx: 184, cy: 48, rx: 9, ry: 4.5, fill: "#ffffff", opacity: 0.9, transform: "rotate(-25 184 48)" }));
    g.appendChild(svgEl("ellipse", { cx: 216, cy: 48, rx: 9, ry: 4.5, fill: "#ffffff", opacity: 0.9, transform: "rotate(25 216 48)" }));
    g.appendChild(svgEl("circle", { cx: 200, cy: 28, r: 5, fill: "none", stroke: "#fde047", "stroke-width": 2 }));
  } else if (topper === "snowflake") {
    for (let a = 0; a < 360; a += 60) {
      const rad = (a * Math.PI) / 180;
      g.appendChild(svgEl("line", {
        x1: 200, y1: 48, x2: 200 + 20 * Math.cos(rad), y2: 48 + 20 * Math.sin(rad),
        stroke: "#e0f2fe", "stroke-width": 3.5, "stroke-linecap": "round",
      }));
    }
    g.appendChild(svgEl("circle", { cx: 200, cy: 48, r: 6, fill: "#ffffff" }));
    g.appendChild(svgEl("circle", { cx: 200, cy: 48, r: 3, fill: "#38bdf8" }));
  } else {
    g.appendChild(starShape(200, 48, 24, "#fde047", "#ca8a04"));
    g.appendChild(starShape(200, 48, 12, "#fef9c3", "none"));
  }
}

function applyTreeTheme() {
  const bgKey = state.tree?.bg_theme || "aurora";
  const theme = state.treeThemes?.backgrounds?.[bgKey];
  if (theme) {
    const stops = document.querySelectorAll("#skyGrad stop");
    if (stops.length >= 3) {
      stops[0].setAttribute("stop-color", theme.top || "#050b1a");
      stops[1].setAttribute("stop-color", theme.mid || "#0d1b3a");
      stops[2].setAttribute("stop-color", theme.bot || "#172a4f");
    }
  }
  drawGarlandLights();
  drawTopStar();
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
    g.appendChild(svgEl("circle", { cx: 0, cy: -16, r: 3, fill: "none", stroke: "#facc15", "stroke-width": 1.3 }));
    g.appendChild(svgEl("rect", { x: -3.5, y: -14.5, width: 7, height: 4.5, rx: 1.2, fill: "#eab308", stroke: "#713f12", "stroke-width": 0.6 }));
    g.appendChild(svgEl("circle", { cx: 0, cy: 0, r: 12.5, fill: fillVal, stroke: "rgba(255,255,255,0.22)", "stroke-width": 0.7 }));
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
    g.appendChild(svgEl("rect", { x: -11, y: -6, width: 22, height: 17, rx: 2.5, fill: fillVal, stroke: "rgba(0,0,0,0.45)" }));
    g.appendChild(svgEl("rect", { x: -12.5, y: -10.5, width: 25, height: 6, rx: 2, fill: fillVal, stroke: "rgba(0,0,0,0.45)" }));
    g.appendChild(svgEl("rect", { x: -2.2, y: -10.5, width: 4.4, height: 21.5, fill: "#fde047" }));
    g.appendChild(svgEl("rect", { x: -11, y: 0, width: 22, height: 3.6, fill: "#fde047" }));
    g.appendChild(svgEl("ellipse", { cx: -4.5, cy: -12.5, rx: 4.5, ry: 2.6, fill: "none", stroke: "#fde047", "stroke-width": 2.2, transform: "rotate(-20 -4.5 -12.5)" }));
    g.appendChild(svgEl("ellipse", { cx: 4.5, cy: -12.5, rx: 4.5, ry: 2.6, fill: "none", stroke: "#fde047", "stroke-width": 2.2, transform: "rotate(20 4.5 -12.5)" }));
  } else if (type === "bell") {
    g.appendChild(svgEl("circle", { cx: -4, cy: -11, r: 3, fill: "#ef4444" }));
    g.appendChild(svgEl("circle", { cx: 4, cy: -11, r: 3, fill: "#ef4444" }));
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
    g.appendChild(svgEl("polygon", { points: "-8,0 -17,-7 -15,0 -17,7", fill: fillVal, stroke: "rgba(0,0,0,0.35)" }));
    g.appendChild(svgEl("polygon", { points: "8,0 17,-7 15,0 17,7", fill: fillVal, stroke: "rgba(0,0,0,0.35)" }));
    g.appendChild(svgEl("circle", { cx: 0, cy: 0, r: 9.5, fill: fillVal, stroke: "rgba(255,255,255,0.35)", "stroke-width": 0.8 }));
    g.appendChild(svgEl("path", { d: "M -6,-5 Q 0,0 6,5 M -6,5 Q 0,0 6,-5", stroke: "#ffffff", "stroke-width": 2.2, "stroke-linecap": "round", opacity: 0.85 }));
    g.appendChild(svgEl("circle", { cx: -3, cy: -3.5, r: 2.2, fill: "#ffffff", opacity: 0.65 }));
  } else if (type === "angel") {
    g.appendChild(svgEl("circle", { cx: 0, cy: -8, r: 7, fill: colorHex, stroke: "#b45309", "stroke-width": 1 }));
    g.appendChild(svgEl("path", { d: "M -10,10 Q 0,2 10,10 L 8,14 Q 0,10 -8,14 Z", fill: "#ffffff", stroke: "#cbd5e1", "stroke-width": 1 }));
    g.appendChild(svgEl("ellipse", { cx: -11, cy: -2, rx: 7, ry: 3.5, fill: "#ffffff", opacity: 0.9, transform: "rotate(-30 -11 -2)" }));
    g.appendChild(svgEl("ellipse", { cx: 11, cy: -2, rx: 7, ry: 3.5, fill: "#ffffff", opacity: 0.9, transform: "rotate(30 11 -2)" }));
    g.appendChild(svgEl("circle", { cx: 0, cy: -18, r: 4, fill: "none", stroke: "#fde047", "stroke-width": 1.8 }));
    g.appendChild(svgEl("circle", { cx: -2.5, cy: -9, r: 1.2, fill: "#1e293b" }));
    g.appendChild(svgEl("circle", { cx: 2.5, cy: -9, r: 1.2, fill: "#1e293b" }));
  } else if (type === "crystal") {
    g.appendChild(svgEl("path", {
      d: "M 0,-14 L 9,-4 L 6,12 L -6,12 L -9,-4 Z",
      fill: colorHex, stroke: "#ffffff", "stroke-width": 1.2, opacity: 0.95,
    }));
    g.appendChild(svgEl("path", { d: "M 0,-14 L 0,12 M -9,-4 L 9,-4", stroke: "#ffffff", "stroke-width": 1, opacity: 0.7 }));
    g.appendChild(svgEl("path", { d: "M -4,-10 L -1,-5 L -4,2", stroke: "#ffffff", "stroke-width": 1.6, fill: "none", opacity: 0.9 }));
    g.appendChild(svgEl("circle", { cx: 0, cy: 0, r: 16, fill: colorHex, opacity: 0.18 }));
  }
  return g;
}

function renderDecorations() {
  decorLayer.innerHTML = "";
  for (const d of state.decorations) {
    const colorHex = state.ornaments[d.ornament_type]?.colors?.[d.color] || "#e63946";
    const x = (d.x / 100) * 400;
    const y = (d.y / 100) * 500;
    const el = ornamentShape(d.ornament_type, d.color, colorHex, x, y);
    el.dataset.id = d.id;
    // Индикатор пожелания 💌
    if (d.wish_text && String(d.wish_text).trim()) {
      const badge = svgEl("text", {
        x: 11, y: -12, "font-size": 11, class: "wish-badge",
        style: "pointer-events:none",
      });
      badge.textContent = "💌";
      el.appendChild(badge);
    }

    el.addEventListener("pointerdown", (e) => {
      e.stopPropagation();
      const isOwn = !state.myUserId || d.user_id === state.myUserId;
      try { el.setPointerCapture(e.pointerId); } catch (err) {}
      dragState = {
        dec: d,
        el,
        startX: e.clientX,
        startY: e.clientY,
        moved: false,
        curX: d.x,
        curY: d.y,
        readOnly: !isOwn,
      };
    });

    el.addEventListener("pointermove", (e) => {
      if (!dragState || dragState.dec.id !== d.id) return;
      const dist = Math.hypot(e.clientX - dragState.startX, e.clientY - dragState.startY);
      if (dist > 6) dragState.moved = true;
      if (dragState.moved && !dragState.readOnly) {
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
      if (finishedDrag.moved && !finishedDrag.readOnly) {
        spawnParticles(e.clientX, e.clientY, colorHex, 14);
        await saveMoveDecoration(d.id, finishedDrag.curX, finishedDrag.curY);
      } else if (!finishedDrag.moved) {
        openOrnamentModal(d);
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
// 8. ЛИДЕРБОРД (ИГРОКИ, ОБОРОТ МОНЕТ, КОМАНДНЫЕ ЁЛКИ, ТЕКУЩАЯ ЁЛКА)
// ============================================================================
function getDisplayName(row) {
  if (row.chat_title) return row.chat_title;
  // В топе показываем человеческое имя, а не @username
  const name = (row.first_name || "").trim();
  if (name && name !== "Участник" && name !== "Игрок") return name;
  if (row.username) return row.username;
  return `Игрок #${row.user_id}`;
}

function getInitials(row) {
  const name = (row.chat_title || row.first_name || row.username || "🎄").trim();
  return name.slice(0, 1).toUpperCase();
}

function getRankSubline(row) {
  if (!row.username) return "";
  return `@${row.username}`;
}

function renderLeaderboard() {
  const podiumEl = $("#lbPodium");
  const listEl = $("#leaderboardList");
  if (!podiumEl || !listEl) return;

  let rows = [];
  const mode = state.activeLbTab;
  if (mode === "by_turnover") {
    rows = state.leaderboard?.by_turnover || [];
  } else if (mode === "team_trees") {
    rows = state.leaderboard?.team_trees || [];
  } else if (mode === "chat_stats") {
    rows = state.stats || [];
  } else {
    rows = state.leaderboard?.by_toys || [];
  }

  podiumEl.innerHTML = "";
  listEl.innerHTML = "";

  if (!rows.length) {
    listEl.innerHTML = `<li class="lb-row"><span>${
      mode === "team_trees"
        ? "Пока нет командных ёлок. Создай свою во вкладке «🎄 Ёлка» → «👥 + С друзьями»!"
        : "Пока нет участников"
    }</span></li>`;
    return;
  }

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
      const scoreText = mode === "by_turnover"
        ? `${item.coin_turnover ?? item.coins ?? 0} 🪙`
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

  rows.forEach((row, idx) => {
    const isTeamMode = mode === "team_trees";
    const isMe = isTeamMode
      ? String(row.chat_id) === String(chatId)
      : Number(row.user_id) === Number(state.myUserId);
    const li = document.createElement("li");
    li.className = "lb-row" + (isMe ? " is-me" : "");
    const medal = ["🥇", "🥈", "🥉"][idx] || `${idx + 1}.`;

    let mainMetric = `${row.count ?? 0} 🎄`;
    let subMetric = `Оборот: ${row.coin_turnover ?? row.coins ?? 0} 🪙`;
    if (mode === "by_turnover") {
      mainMetric = `${row.coin_turnover ?? row.coins ?? 0} 🪙`;
      subMetric = `Наряжено игрушек: ${row.count ?? 0} 🎄`;
    } else if (isTeamMode) {
      mainMetric = `${row.count ?? 0} 🎄`;
      subMetric = `Участников в команде: ${Math.max(1, row.members_count || 1)} 👥`;
    }

    li.innerHTML = `
      <div class="lb-left">
        <span class="lb-rank">${medal}</span>
        <div class="lb-avatar">${escapeHtml(getInitials(row))}</div>
        <div class="lb-user-meta">
          <div class="lb-uname">${escapeHtml(getDisplayName(row))} ${isMe ? `<b>${isTeamMode ? "(Открыта)" : "(Вы)"}</b>` : ""}</div>
          <div class="lb-sub">${subMetric}</div>
          ${!isTeamMode && getRankSubline(row) ? `<div class="lb-handle">${escapeHtml(getRankSubline(row))}</div>` : ""}
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
// 9. ИНВЕНТАРЬ, МАГАЗИН И ДОНАТ (TELEGRAM STARS)
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
  // 🎰 Сюрприз-бокс (Гача) — карточка сверху
  const loot = document.createElement("div");
  loot.className = "lootbox-card";
  const pool = getLootboxPool();
  loot.innerHTML = `
    <div class="s-emoji">🎰</div>
    <div class="s-title">Новогодний Сюрприз-бокс</div>
    <p>Всегда <b>${state.lootboxPrice} 🪙</b> за открытие. Внутри:</p>
    <div class="slot-strip">${pool
      .map(
        (p) => `<div class="slot-mini">
          <span class="slot-emoji">${state.ornaments?.[p.item]?.emoji || "🎁"}</span>
          <span class="slot-coins">+${p.coins} 🪙</span>
        </div>`,
      )
      .join("")}</div>
    <button type="button" class="buy-coin-btn" id="lootboxOpenBtn">Открыть за ${state.lootboxPrice} 🪙</button>
  `;
  loot.querySelector("#lootboxOpenBtn").addEventListener("click", (ev) => {
    openLootbox(ev.clientX, ev.clientY);
  });
  grid.appendChild(loot);
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
      <div class="donate-btns donate-btns-single">
        <button type="button" class="pay-stars-btn" data-pack="${packId}">
          ⭐️ ${pack.stars_price} Stars
        </button>
      </div>
    `;
    card.querySelector(".pay-stars-btn").addEventListener("click", () => buyWithStars(packId));
    list.appendChild(card);
  }
}

// ============================================================================
// 9b. АДВЕНТ-КАЛЕНДАРЬ, СТИЛЬ ЁЛКИ, ЛУТБОКС, РЕФЕРАЛКА, КАРТОЧКА ИГРУШКИ
// ============================================================================
function renderAdventModal() {
  const grid = $("#adventGrid");
  if (!grid) return;
  grid.innerHTML = "";
  const rewards = state.adventRewards && state.adventRewards.length ? state.adventRewards : [
    { day: 1, coins: 150, item: "ball", title: "День 1" },
    { day: 2, coins: 250, item: "candy", title: "День 2" },
    { day: 3, coins: 350, item: "snowflake", title: "День 3" },
    { day: 4, coins: 500, item: "bell", title: "День 4" },
    { day: 5, coins: 700, item: "gift", title: "День 5" },
    { day: 6, coins: 1000, item: "star", title: "День 6" },
    { day: 7, coins: 1500, item: "crystal", title: "День 7+" },
  ];
  const streak = Number(state.dailyStreak || 0);
  const nextDay = Math.min(streak + 1, 7);
  for (const r of rewards) {
    const day = Number(r.day);
    const cell = document.createElement("div");
    let cls = "advent-day";
    if (day <= streak) cls += " done";
    else if (day === nextDay && state.canClaimDaily) cls += " today";
    else cls += " locked";
    const emoji = state.ornaments?.[r.item]?.emoji || "🎁";
    cell.className = cls;
    cell.innerHTML = `<span class="ad-emoji">${day <= streak ? "✅" : emoji}</span><b>День ${day}</b><br>+${r.coins} 🪙`;
    grid.appendChild(cell);
  }
  const lbl = $("#adventStreakLabel");
  if (lbl) lbl.textContent = `Твоя серия: ${streak} дн. ${state.canClaimDaily ? "— подарок ждёт! 🎁" : "— приходи завтра!"}`;
  const claimBtn = $("#claimDailyBtn");
  if (claimBtn) {
    claimBtn.disabled = !state.canClaimDaily;
    claimBtn.textContent = state.canClaimDaily ? "🎁 Открыть сегодняшний подарок" : "✅ Сегодня уже открыто — приходи завтра!";
  }
}

async function claimDailyAdvent() {
  try {
    const res = await fetch("/api/daily-claim", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ init_data: initData, user: currentUser }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Не удалось открыть");
    haptic("medium");
    if (data.profile) applyProfile(data.profile);
    toast(data.message || "Подарок получен! 🎁");
    renderAdventModal();
    await refreshTreeData();
  } catch (err) {
    toast(err.message || "Не удалось открыть подарок", true);
  }
}

function resetStyleDraft() {
  state.styleDraft = {
    bg_theme: state.tree?.bg_theme || "aurora",
    garland_style: state.tree?.garland_style || "classic",
    topper_type: state.tree?.topper_type || "star",
  };
}

function renderStyleModal(resetDraft = true) {
  const themes = state.treeThemes;
  if (!themes) return;
  // Черновик сбрасывается только при открытии модалки, иначе клик по варианту
  // перезаписывался старым стилем и «ничего не переключалось».
  if (resetDraft) resetStyleDraft();
  const mk = (containerId, dict, key) => {
    const box = document.getElementById(containerId);
    if (!box) return;
    box.innerHTML = "";
    for (const [k, v] of Object.entries(dict || {})) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "style-opt" + (state.styleDraft[key] === k ? " selected" : "");
      b.textContent = v.name || k;
      b.onclick = () => {
        state.styleDraft[key] = k;
        haptic("light");
        renderStyleModal(false);
        // Мгновенный предпросмотр на ёлке (без сохранения)
        previewStyleDraft();
      };
      box.appendChild(b);
    }
  };
  mk("bgThemeOptions", themes.backgrounds, "bg_theme");
  mk("garlandOptions", themes.garlands, "garland_style");
  mk("topperOptions", themes.toppers, "topper_type");
}

async function saveTreeStyle() {
  try {
    const res = await fetch("/api/tree-style", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chat_id: Number(requestChatId()),
        bg_theme: state.styleDraft.bg_theme,
        garland_style: state.styleDraft.garland_style,
        topper_type: state.styleDraft.topper_type,
        init_data: initData,
        user: currentUser,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Не удалось сохранить");
    state.tree = data.tree;
    applyTreeTheme();
    haptic("medium");
    toast(data.message || "Стиль ёлки обновлён! 🎨");
    $("#styleModal").classList.add("hidden");
  } catch (err) {
    toast(err.message || "Не удалось сохранить стиль", true);
  }
}

// Набор призов бокса (приходит с сервера, чтобы игрок заранее видел, что выпадает)
function getLootboxPool() {
  if (Array.isArray(state.lootboxPool) && state.lootboxPool.length) return state.lootboxPool;
  return [
    { item: "gift", coins: 40, weight: 26 },
    { item: "star", coins: 50, weight: 24 },
    { item: "angel", coins: 75, weight: 20 },
    { item: "crystal", coins: 100, weight: 15 },
    { item: "bell", coins: 300, weight: 15 },
  ];
}

// ============================================================================
// 9c. СЛОТ-МАШИНА: показываем какой приз выпадает
// ============================================================================
const SLOT_SYMBOLS = ["gift", "star", "angel", "crystal", "bell"];

function buildSlotColumn(pool, finalItem) {
  // Лента из случайных призов + нужный символ через 2 позиции от конца
  const tape = [];
  for (let i = 0; i < 18; i++) {
    tape.push(pool[Math.floor(Math.random() * pool.length)]);
  }
  const finalIdx = pool.findIndex((p) => p.item === finalItem);
  tape.push(pool[finalIdx >= 0 ? finalIdx : 0]);
  tape.push(pool[Math.floor(Math.random() * pool.length)]);
  return tape;
}

function renderSlotTape(el, tape) {
  el.innerHTML = tape
    .map(
      (p) => `<div class="slot-cell">
        <span class="slot-emoji">${state.ornaments?.[p.item]?.emoji || "🎁"}</span>
        <span class="slot-coins">+${p.coins} 🪙</span>
      </div>`,
    )
    .join("");
  return tape.length;
}

async function openLootbox(clientX, clientY) {
  await flushPendingClicks();
  if (state.coins < state.lootboxPrice) {
    toast(`Нужно ${state.lootboxPrice} 🪙 для открытия Сюрприз-бокса!`, true);
    return;
  }
  const pool = getLootboxPool();
  // Сначала запускаем анимацию слотов, а результат запрашиваем параллельно
  const modal = $("#lootboxModal");
  const reels = [$("#slotReel1"), $("#slotReel2"), $("#slotReel3")];
  const resultText = $("#lootboxPrizeText");
  const resultEmoji = $("#lootboxPrizeEmoji");
  if (resultText) resultText.textContent = "Крутим слоты…";
  if (resultEmoji) resultEmoji.textContent = "🎰";
  modal.classList.remove("hidden");
  modal.classList.add("spinning");
  const okBtn = $("#lootboxOkBtn");
  if (okBtn) {
    okBtn.disabled = true;
    okBtn.textContent = "Крутим…";
  }
  reels.forEach((reel, idx) => {
    if (!reel) return;
    const tape = buildSlotColumn(pool, SLOT_SYMBOLS[(idx + 1) % SLOT_SYMBOLS.length]);
    const cells = renderSlotTape(reel, tape);
    reel.style.transition = "none";
    reel.style.transform = "translateY(0)";
    reel.dataset.cells = String(cells);
  });

  try {
    const res = await fetch("/api/lootbox", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ init_data: initData, user: currentUser }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Не удалось открыть бокс");
    haptic("medium");
    if (clientX && clientY) spawnParticles(clientX, clientY, "#c084fc", 30);
    if (data.profile) applyProfile(data.profile);
    const prize = data.prize || {};
    const emoji = state.ornaments?.[prize.item]?.emoji || "🎁";

    // Останавливаем каждый барабан на выпавшем призе
    reels.forEach((reel, idx) => {
      if (!reel) return;
      const tape = buildSlotColumn(pool, prize.item);
      const cells = renderSlotTape(reel, tape);
      reel.dataset.cells = String(cells);
      const cellH = 58;
      const target = -(cells - 2) * cellH; // нужный символ — предпоследний
      reel.style.transition = "none";
      reel.style.transform = "translateY(0)";
      void reel.offsetHeight; // reflow, чтобы анимация точно стартовала
      const delay = 140 + idx * 260;
      setTimeout(() => {
        reel.style.transition = `transform ${1.35 + idx * 0.45}s cubic-bezier(0.12, 0.75, 0.05, 1)`;
        reel.style.transform = `translateY(${target}px)`;
        haptic("light");
      }, delay);
    });

    const totalSpin = 1350 + 2 * 450 + 260;
    setTimeout(() => {
      haptic("heavy");
      modal.classList.remove("spinning");
      modal.classList.add("won");
      if (resultEmoji) resultEmoji.textContent = emoji;
      if (resultText) resultText.textContent = data.message || "Приз получен!";
      if (okBtn) {
        okBtn.disabled = false;
        okBtn.textContent = "Забрать приз 🎉";
      }
      refreshTreeData().catch(() => {});
    }, totalSpin);
  } catch (err) {
    modal.classList.remove("spinning");
    modal.classList.add("hidden");
    if (okBtn) {
      okBtn.disabled = false;
      okBtn.textContent = "Забрать приз 🎉";
    }
    toast(err.message || `Не хватает монет на бокс (${state.lootboxPrice} 🪙)`, true);
  }
}

function getReferralLink() {
  if (state.botUsername) return `https://t.me/${state.botUsername}?start=ref_${currentUser.id}`;
  return `${window.location.origin}/?ref=${currentUser.id}`;
}

async function shareReferral() {
  const link = getReferralLink();
  const text = `🎄 Приходи наряжать новогоднюю ёлку со мной! За регистрацию по моей ссылке мы оба получим +300 🪙 и игрушки 🎁⭐`;
  haptic("light");
  if (tg?.openTelegramLink) {
    try { tg.openTelegramLink(`https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(text)}`); return; } catch (e) {}
  }
  try {
    await navigator.clipboard.writeText(link);
    toast("Ссылка скопирована! Отправь её другу 🎁");
  } catch (e) {
    toast(link);
  }
}

function openOrnamentModal(d) {
  state.activeOrnament = d;
  const info = state.ornaments?.[d.ornament_type];
  const owner = d.username ? `@${d.username}` : (d.first_name || "Другой игрок");
  const isOwn = !state.myUserId || d.user_id === state.myUserId;
  $("#ornamentModalTitle").textContent = `${info?.emoji || "🎄"} ${info?.name || "Игрушка"}`;
  $("#ornamentAuthor").textContent = `Повесил(а): ${owner}${isOwn ? " (это ты!)" : ""}`;
  const wish = (d.wish_text || "").trim();
  const wishBox = $("#ornamentWishBox");
  if (wish) {
    wishBox.classList.remove("hidden");
    $("#ornamentWishText").textContent = wish;
  } else {
    wishBox.classList.add("hidden");
  }
  $("#removeOrnamentBtn").classList.toggle("hidden", !isOwn);
  $("#ornamentModal").classList.remove("hidden");
  haptic("light");
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

// ============================================================================
// 10. КЛИКЕР С ОБОРОТОМ МОНЕТ И КОМБО
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
  state.coinTurnover += state.clickPower;
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
// 11. ЗАГРУЗКА ЁЛКИ, УКРАШЕНИЕ И СИНХРОНИЗАЦИЯ
// ============================================================================
let treeFetchSeq = 0;
let lastAppliedSeq = 0;

async function refreshTreeData(inviteOverride = "") {
  const q = new URLSearchParams({
    user_id: String(currentUser.id),
    username: currentUser.username || "",
    first_name: currentUser.first_name || "Игрок",
    invite_code: inviteOverride,
    t: String(Date.now()),
  });
  if (urlReferrerId) q.set("referrer_id", String(urlReferrerId));
  const requestedChat = requestChatId();
  const mySeq = ++treeFetchSeq;
  const res = await fetch(`/api/tree/${requestedChat}?${q.toString()}`, { cache: "no-store" });
  if (!res.ok) throw new Error(await res.text());
  const data = await res.json();
  // Пока шёл запрос, мог прийти более свежий ответ — старый не применяем,
  // иначе игрушки «пропадают» с ёлки. Если ёлку успели переключить — тоже мимо.
  if (mySeq < lastAppliedSeq || String(requestedChat) !== requestChatId()) {
    return;
  }
  lastAppliedSeq = mySeq;
  state.tree = data.tree;
  if (data.tree && data.tree.chat_id) {
    chatId = String(data.tree.chat_id);
  }
  state.isPersonalTree = data.is_personal_tree !== false;
  if (data.personal_tree_id) state.personalTreeId = String(data.personal_tree_id);
  state.members = Array.isArray(data.members) ? data.members : [];
  state.membersCount = Number(data.members_count || state.members.length || 0);
  if (data.team_tree !== undefined) {
    state.teamTree = data.team_tree || null;
  }
  state.ornaments = data.ornaments;
  state.donatePacks = data.donate_packs || {};
  state.botUsername = data.bot_username || "";
  state.webappUrl = data.webapp_url || window.location.origin;
  state.treeThemes = data.tree_themes || state.treeThemes;
  state.lootboxPrice = Number(data.lootbox_price || 100);
  if (Array.isArray(data.lootbox_pool) && data.lootbox_pool.length) state.lootboxPool = data.lootbox_pool;
  if (Array.isArray(data.nft_catalog)) state.nftCatalog = data.nft_catalog;
  if (Array.isArray(data.nft_gifts)) state.nftGifts = data.nft_gifts;
  state.nftMintEnabled = !!data.nft_mint_enabled;
  state.adventRewards = data.advent_rewards || state.adventRewards;
  state.decorations = data.decorations || [];
  state.stats = data.stats || [];
  if (data.leaderboard) {
    state.leaderboard = data.leaderboard;
  }
  if (data.profile) {
    applyProfile(data.profile);
  }
  if (data.referral_bonus_applied) {
    toast("🎁 Бонус за приглашение: +300 🪙 и игрушки обоим!");
    urlReferrerId = 0;
  }
  $("#chatTitle").textContent = data.tree.chat_title ? `${data.tree.chat_title}` : "Общая новогодняя ёлка";
  if (data.tree.is_finished) {
    $("#hint").textContent = "🎉 Ивент завершён! С Новым годом!";
  }
  renderTreeSwitcher();
  renderCrowd();
  updateHeaderAndClickerUI();
  updateDailyUI();
  applyTreeTheme();
  renderPalette();
  renderShop();
  renderDonateShop();
  renderDecorations();
  renderLeaderboard();
  renderPostcardGifts(data.nft_gifts || []);
  schedulePostcardRefresh();
  saveBackup();
}

async function initLoadAndSync() {
  try {
    await refreshTreeData(urlInviteCode);
    const backup = loadLocalBackup();
    if (backup) {
      const myServerDecs = state.decorations.filter((d) => d.user_id === state.myUserId);
      // Игрушки из бэкапа восстанавливаем только если на ёлке их нет совсем И сервер
      // не прислал ни одной (иначе получались дубли, а после удаления — «воскрешение»).
      const needSync =
        (backup.coins && backup.coins > state.coins) ||
        (backup.coin_turnover && backup.coin_turnover > state.coinTurnover) ||
        (backup.click_power && backup.click_power > state.clickPower) ||
        (state.decorations.length === 0 &&
          myServerDecs.length === 0 &&
          Array.isArray(backup.decorations) &&
          backup.decorations.length > 0);
      if (needSync) {
        const syncRes = await fetch("/api/sync", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            chat_id: Number(requestChatId()),
            coins: backup.coins,
            coin_turnover: backup.coin_turnover,
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
  // Тап по игрушке — карточка с автором и пожеланием (снятие — кнопкой внутри)
  openOrnamentModal(d);
}

async function removeActiveOrnament() {
  const d = state.activeOrnament;
  if (!d) return;
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
    $("#ornamentModal").classList.add("hidden");
    state.activeOrnament = null;
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

  const wishText = ($("#wishInput")?.value || "").trim().slice(0, 120);
  try {
    const res = await fetch("/api/decorate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chat_id: Number(requestChatId()),
        ornament_type: state.selectedType,
        color: state.selectedColor,
        x: pt.x,
        y: pt.y,
        wish_text: wishText,
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
    toast(wishText ? "Игрушка с пожеланием повешена! 💌" : "Игрушка повешена на ёлку! ✨");
    if ($("#wishInput")) $("#wishInput").value = "";
    if (data.profile) applyProfile(data.profile);
    await refreshTreeData();
  } catch (err) {
    toast(err.message || "Не удалось повесить", true);
  }
});

// ============================================================================
// 12. ИТОГОВАЯ ОТКРЫТКА: живое превью, скачивание, шаринг и NFT-подарки
// ============================================================================
let postcardTimer = null;
let postcardLoading = false;
let postcardBlobUrl = null;

function postcardUrl() {
  return `/api/final-image/${requestChatId()}?user_id=${currentUser.id}&t=${Date.now()}`;
}

function renderPostcardGifts(gifts) {
  const boxes = [$("#postcardGifts"), $("#previewGifts")].filter(Boolean);
  for (const box of boxes) {
    box.innerHTML = "";
    const list = Array.isArray(gifts) ? gifts : [];
    if (!list.length) {
      box.innerHTML = `<div class="gift-empty">🎁 Подарков пока нет — прикрепи NFT-подарок к открытке, и он появится на ней.</div>`;
      continue;
    }
    for (const g of list.slice(0, 6)) {
      const card = document.createElement("div");
      card.className = "gift-chip";
      card.innerHTML = `
        <span class="gift-emoji">${g.emoji || "🎁"}</span>
        <span class="gift-meta">
          <b>${escapeHtml(g.title || "NFT-подарок")}</b>
          <small>от ${escapeHtml(g.from_name || "друга")}</small>
        </span>
      `;
      box.appendChild(card);
    }
  }
}

async function loadPostcard(force = false) {
  const img = $("#postcardImg");
  const skeleton = $("#postcardSkeleton");
  if (!img || postcardLoading) return;
  postcardLoading = true;
  try {
    const res = await fetch(postcardUrl(), { cache: "no-store" });
    if (!res.ok) throw new Error("Не удалось собрать открытку");
    const blob = await res.blob();
    if (postcardBlobUrl) URL.revokeObjectURL(postcardBlobUrl);
    postcardBlobUrl = URL.createObjectURL(blob);
    img.src = postcardBlobUrl;
    img.classList.add("loaded");
    skeleton?.classList.add("hidden");
  } catch (e) {
    if (skeleton) {
      skeleton.textContent = "Не удалось собрать открытку 😢 Нажми 🔄";
      skeleton.classList.remove("hidden");
    }
  } finally {
    postcardLoading = false;
  }
}

function schedulePostcardRefresh() {
  clearTimeout(postcardTimer);
  postcardTimer = setTimeout(() => loadPostcard(), 1200);
}

async function downloadPostcard() {
  try {
    haptic("medium");
    const blob = postcardBlobUrl ? await (await fetch(postcardBlobUrl)).blob() : await (await fetch(postcardUrl())).blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `newyear-tree-${Date.now()}.png`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
    toast("Открытка сохранена! 🖼");
  } catch (e) {
    toast("Не удалось скачать открытку", true);
  }
}

async function sharePostcard() {
  const text = "🎄 Наша новогодняя ёлка! С Новым годом!";
  haptic("light");
  try {
    const blob = await (await fetch(postcardUrl())).blob();
    const file = new File([blob], "newyear-tree.png", { type: "image/png" });
    if (navigator.canShare?.({ files: [file] })) {
      await navigator.share({ files: [file], text });
      return;
    }
  } catch (e) {}
  const link = `${state.webappUrl || window.location.origin}`;
  const shareLink = `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(text)}`;
  if (tg?.openTelegramLink) {
    tg.openTelegramLink(shareLink);
  } else {
    try {
      await navigator.clipboard.writeText(link);
      toast("Ссылка на ёлку скопирована 📋");
    } catch (e) {
      toast(link);
    }
  }
}

function openPostcardFullscreen() {
  $("#previewImg").src = $("#postcardImg")?.src || postcardUrl();
  $("#previewModal").classList.remove("hidden");
}

$("#previewBtn")?.addEventListener("click", openPostcardFullscreen);
$("#postcardOpenBtn")?.addEventListener("click", openPostcardFullscreen);
$("#postcardRefreshBtn")?.addEventListener("click", () => {
  haptic("light");
  loadPostcard(true);
});
// ── NFT-подарки ────────────────────────────────────────────────────────────
function renderNftCatalog() {
  const box = $("#nftCatalog");
  if (!box) return;
  const catalog = Array.isArray(state.nftCatalog) ? state.nftCatalog : [];
  box.innerHTML = "";
  const rarityNames = {
    common: "обычный",
    rare: "редкий",
    epic: "эпический",
    legendary: "легендарный",
    mythic: "мифический",
  };
  for (const item of catalog) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "nft-card" + (Number(state.nftDraftToken) === Number(item.token_id) ? " selected" : "");
    card.innerHTML = `
      <span class="nft-emoji">${item.emoji}</span>
      <span class="nft-meta">
        <b>${escapeHtml(item.title)}</b>
        <small>${escapeHtml(item.subtitle || "")} · ${rarityNames[item.rarity] || item.rarity}</small>
      </span>
    `;
    card.onclick = () => {
      state.nftDraftToken = Number(item.token_id);
      haptic("light");
      renderNftCatalog();
    };
    box.appendChild(card);
  }
}

function renderNftRecipients() {
  const box = $("#nftToOptions");
  if (!box) return;
  box.innerHTML = "";
  const members = (state.members || []).filter((m) => Number(m.user_id) !== Number(state.myUserId));
  if (!members.length) {
    box.innerHTML = `<div class="gift-empty">Нет других участников: введи ID друга вручную ниже 👇</div>`;
    return;
  }
  for (const m of members) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "nft-to-chip" + (Number(state.nftDraftTo) === Number(m.user_id) ? " selected" : "");
    chip.textContent = `${m.first_name || "Друг"} (#${m.user_id})`;
    chip.onclick = () => {
      state.nftDraftTo = Number(m.user_id);
      $("#nftToInput").value = String(m.user_id);
      haptic("light");
      renderNftRecipients();
    };
    box.appendChild(chip);
  }
}

function openNftGiftModal() {
  if (!Array.isArray(state.nftCatalog) || !state.nftCatalog.length) {
    toast("Коллекция подарков ещё не загружена", true);
    return;
  }
  state.nftDraftToken = state.nftDraftToken || Number(state.nftCatalog[0].token_id);
  renderNftRecipients();
  renderNftCatalog();
  $("#nftGiftModal").classList.remove("hidden");
}

async function sendNftGift() {
  const toUserId = Number($("#nftToInput").value || state.nftDraftTo || 0);
  if (!toUserId) {
    toast("Укажи, кому подарить (ID друга)", true);
    return;
  }
  if (!state.nftDraftToken) {
    toast("Выбери подарок из коллекции", true);
    return;
  }
  try {
    const res = await fetch("/api/nft-gifts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        to_user_id: toUserId,
        token_id: Number(state.nftDraftToken),
        message: ($("#nftMessageInput").value || "").trim(),
        init_data: initData,
        user: currentUser,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Не удалось прикрепить подарок");
    haptic("heavy");
    toast(`Подарок «${data.item?.title || "NFT"}» прикреплён к открытке! 🎁`);
    $("#nftGiftModal").classList.add("hidden");
    $("#nftMessageInput").value = "";
    await refreshTreeData();
    loadPostcard(true);
  } catch (err) {
    toast(err.message || "Не удалось отправить подарок", true);
  }
}

$("#postcardGiftBtn")?.addEventListener("click", openNftGiftModal);
$("#closeNftGiftModalBtn")?.addEventListener("click", () => $("#nftGiftModal").classList.add("hidden"));
$("#nftGiftModal")?.addEventListener("click", (e) => {
  if (e.target === $("#nftGiftModal")) $("#nftGiftModal").classList.add("hidden");
});
$("#sendNftGiftBtn")?.addEventListener("click", sendNftGift);

$("#postcardDownloadBtn")?.addEventListener("click", downloadPostcard);
$("#previewDownloadBtn")?.addEventListener("click", downloadPostcard);
$("#postcardShareBtn")?.addEventListener("click", sharePostcard);
$("#previewShareBtn")?.addEventListener("click", sharePostcard);

$("#closeModalBtn").addEventListener("click", () => {
  $("#previewModal").classList.add("hidden");
});

$("#previewModal").addEventListener("click", (e) => {
  if (e.target === $("#previewModal")) {
    $("#previewModal").classList.add("hidden");
  }
});

// --- v7: Адвент, стиль, рефералка, игрушка, лутбокс ---
$("#dailyGiftBtn").addEventListener("click", () => {
  renderAdventModal();
  $("#adventModal").classList.remove("hidden");
});
$("#closeAdventModalBtn").addEventListener("click", () => $("#adventModal").classList.add("hidden"));
$("#adventModal").addEventListener("click", (e) => { if (e.target === $("#adventModal")) $("#adventModal").classList.add("hidden"); });
$("#claimDailyBtn").addEventListener("click", claimDailyAdvent);

$("#openStyleModalBtn").addEventListener("click", () => {
  resetStyleDraft();
  renderStyleModal(false);
  $("#styleModal").classList.remove("hidden");
});
$("#closeStyleModalBtn").addEventListener("click", () => $("#styleModal").classList.add("hidden"));
$("#styleModal").addEventListener("click", (e) => { if (e.target === $("#styleModal")) $("#styleModal").classList.add("hidden"); });
$("#saveStyleBtn").addEventListener("click", saveTreeStyle);

$("#shareReferralBtn").addEventListener("click", shareReferral);

$("#closeOrnamentModalBtn").addEventListener("click", () => $("#ornamentModal").classList.add("hidden"));
$("#ornamentModal").addEventListener("click", (e) => { if (e.target === $("#ornamentModal")) $("#ornamentModal").classList.add("hidden"); });
$("#removeOrnamentBtn").addEventListener("click", removeActiveOrnament);

$("#closeLootboxModalBtn").addEventListener("click", () => $("#lootboxModal").classList.add("hidden"));
$("#lootboxOkBtn").addEventListener("click", () => $("#lootboxModal").classList.add("hidden"));
$("#lootboxModal").addEventListener("click", (e) => { if (e.target === $("#lootboxModal")) $("#lootboxModal").classList.add("hidden"); });

drawSnowAndStars();
drawGarlandLights();
drawTopStar();
updateCountdown();
setInterval(updateCountdown, 30000);
setInterval(() => {
  refreshTreeData().catch(() => {});
}, 12000);
initLoadAndSync();
