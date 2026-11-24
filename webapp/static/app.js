const tg = window.Telegram?.WebApp;
if (tg) {
  tg.ready();
  tg.expand();
}

const params = new URLSearchParams(window.location.search);
const urlChatId = params.get("chat_id") || params.get("startapp") || tg?.initDataUnsafe?.start_param || "";
if (urlChatId) {
  try { localStorage.setItem("ny_last_chat_id", String(urlChatId)); } catch (e) {}
}
const savedChatId = (() => {
  try { return localStorage.getItem("ny_last_chat_id") || ""; } catch (e) { return ""; }
})();
const chatId = urlChatId || savedChatId || String(tg?.initDataUnsafe?.chat?.id || tg?.initDataUnsafe?.user?.id || "1");
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
const BACKUP_KEY = `ny_backup_v3_${chatId}_${currentUser.id}`;

let state = {
  ornaments: {},
  donatePacks: {},
  gramWallet: "",
  selectedType: "ball",
  selectedColor: "red",
  decorations: [],
  stats: [],
  myUserId: currentUser.id,
  coins: 50,
  clickPower: 1,
  inventory: { ball: 2, snowflake: 1 },
  energy: 500,
  maxEnergy: 500,
  pendingClicks: 0,
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

// --- Локальный и облачный бэкап прогресса ---
function saveBackup() {
  const payload = {
    coins: state.coins,
    click_power: state.clickPower,
    inventory: state.inventory,
    decorations: state.decorations,
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

// --- Переключение вкладок ---
function switchTab(tabName) {
  $$(".tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === tabName));
  $$(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${tabName}`));
  haptic("light");
}

$$(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});

$("#balancePill").addEventListener("click", () => switchTab("clicker"));

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
      setTimeout(() => { suppressNextTreeClick = false; }, 100);
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
  $("#counter").textContent = `На ёлке: ${state.decorations.length}`;
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
    card.querySelector(".buy-coin-btn").addEventListener("click", () => buyOrnamentWithCoins(type));
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

async function buyOrnamentWithCoins(ornamentType) {
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
    applyProfile(data.profile);
    state.selectedType = ornamentType;
    state.selectedColor = Object.keys(state.ornaments[ornamentType].colors)[0];
    renderPalette();
    toast(data.message || "Игрушка куплена! 🎉");
  } catch (err) {
    toast(err.message || "Не хватает монет", true);
  }
}

// --- Донат: Telegram Stars и GRAM ---
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

// --- Кликер ---
const bigClickBtn = $("#bigClickBtn");
const clickerStage = $("#clickerStage");

bigClickBtn.addEventListener("pointerdown", (e) => {
  e.preventDefault();
  if (state.energy <= 0) {
    toast("Энергия закончилась! Подожди пару секунд ⚡", true);
    return;
  }
  state.energy = Math.max(0, state.energy - 1);
  state.coins += state.clickPower;
  state.pendingClicks += 1;
  haptic("light");
  updateHeaderAndClickerUI();
  saveBackup();

  // Анимация +X 🪙
  const rect = clickerStage.getBoundingClientRect();
  const fx = (e.clientX ? e.clientX - rect.left : rect.width / 2) + (Math.random() * 30 - 15);
  const fy = (e.clientY ? e.clientY - rect.top : rect.height / 2) - 10;
  const plus = document.createElement("div");
  plus.className = "float-plus";
  plus.textContent = `+${state.clickPower} 🪙`;
  plus.style.left = `${fx}px`;
  plus.style.top = `${fy}px`;
  clickerStage.appendChild(plus);
  setTimeout(() => plus.remove(), 750);

  clearTimeout(clickFlushTimer);
  clickFlushTimer = setTimeout(flushPendingClicks, 600);
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

$("#upgradeClickBtn").addEventListener("click", async () => {
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
    applyProfile(data.profile);
    toast(data.message || "Сила клика увеличена! ⚡");
  } catch (err) {
    toast(err.message || "Не хватает монет", true);
  }
});

// Регенерация энергии
setInterval(() => {
  if (state.energy < state.maxEnergy) {
    state.energy = Math.min(state.maxEnergy, state.energy + 3);
    updateHeaderAndClickerUI();
  }
}, 1000);

// --- Загрузка и синхронизация ёлки ---
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
  state.decorations = data.decorations;
  state.stats = data.stats;
  if (data.profile) {
    state.coins = Number(data.profile.coins ?? state.coins);
    state.clickPower = Number(data.profile.click_power ?? state.clickPower);
    state.inventory = data.profile.inventory || state.inventory;
  }
  $("#chatTitle").textContent = data.tree.chat_title ? `Чат: ${data.tree.chat_title}` : "Общая ёлка чата";
  if (data.tree.is_finished) {
    $("#hint").textContent = "🎉 Ивент завершён! С Новым годом!";
  }
  updateHeaderAndClickerUI();
  renderPalette();
  renderShop();
  renderDonateShop();
  renderDecorations();
  renderStats();
  saveBackup();
}

async function initLoadAndSync() {
  try {
    await refreshTreeData();
    // Проверяем локальный бэкап (на случай если контейнер Render перезапускался)
    const backup = loadLocalBackup();
    if (backup) {
      const needSync =
        (backup.coins && backup.coins > state.coins) ||
        (backup.click_power && backup.click_power > state.clickPower) ||
        (state.decorations.length === 0 && Array.isArray(backup.decorations) && backup.decorations.length > 0);
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
    toast("Это чужая игрушка 🙂");
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

  const qty = Number(state.inventory?.[state.selectedType] || 0);
  if (qty <= 0) {
    const info = state.ornaments[state.selectedType];
    toast(`В инвентаре нет «${info?.name || "игрушки"}»! Купи в Магазине 🛍`, true);
    return;
  }

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
        user: currentUser,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Ошибка");
    }
    haptic("medium");
    toast("Игрушка повешена на ёлку! 🎄");
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

drawSnow();
drawTopStar();
updateCountdown();
setInterval(updateCountdown, 30000);
initLoadAndSync();
