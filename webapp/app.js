"use strict";
const tg = window.Telegram && window.Telegram.WebApp;
const initData = (tg && tg.initData) || "";
const root = document.getElementById("app");
const layer = document.getElementById("layer");
const tabbar = document.getElementById("tabs");
const LOCALES = { uk: "uk-UA", ru: "ru-RU", es: "es-ES", en: "en-GB" };
const LANG_NAMES = { uk: "Українська", ru: "Русский", es: "Español", en: "English" };
const TABS = ["home", "radar", "docs", "bonus", "profile"];
const TAB_ICONS = { home: "home", radar: "radar", docs: "id", bonus: "gift", profile: "user" };
const NS = "http://www.w3.org/2000/svg";
const ICONS = {
  home: "M3 11.5 12 4l9 7.5M5.5 10v9a1 1 0 0 0 1 1H10v-5.5h4V20h3.5a1 1 0 0 0 1-1v-9",
  radar: "M12 3a9 9 0 1 0 9 9M12 7.5a4.5 4.5 0 1 0 4.5 4.5M12 12l6.5-6.5",
  id: "M5 5h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2ZM9 8.5a2 2 0 1 0 0 4 2 2 0 0 0 0-4ZM5.8 16c.5-1.4 1.7-2.2 3.2-2.2s2.7.8 3.2 2.2M15 10h3M15 14h3",
  gift: "M4 8h16a1 1 0 0 1 1 1v2a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1ZM5 12v7a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-7M12 8v13M12 8S10.5 3 7.5 3a2.5 2.5 0 0 0 0 5M12 8s1.5-5 4.5-5a2.5 2.5 0 0 1 0 5",
  user: "M12 4a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM4.5 20.5c1-3.6 3.9-5.5 7.5-5.5s6.5 1.9 7.5 5.5",
  plus: "M12 5v14M5 12h14",
  search: "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14ZM20 20l-4-4",
  right: "M9 5l7 7-7 7",
  left: "M15 5l-7 7 7 7",
  x: "M6 6l12 12M18 6 6 18",
  check: "M4.5 12.5 10 18l9.5-11",
  pause: "M8 5v14M16 5v14",
  play: "M7 5v14l12-7Z",
  refresh: "M20 11a8 8 0 0 0-14.6-4.4L3 9M3 4v5h5M4 13a8 8 0 0 0 14.6 4.4L21 15M21 20v-5h-5",
  trash: "M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2M6.5 7l1 12a2 2 0 0 0 2 2h5a2 2 0 0 0 2-2l1-12M10 11v6M14 11v6",
  clock: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18ZM12 7v5l3.5 2",
  calendar: "M5 5h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2ZM3 10h18M8 3v4M16 3v4",
  pin: "M12 21s7-6.2 7-11.5a7 7 0 1 0-14 0C5 14.8 12 21 12 21ZM12 7a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5Z",
  bell: "M18 9a6 6 0 1 0-12 0c0 6-2.5 8-2.5 8h17S18 15 18 9ZM10 20.5a2.2 2.2 0 0 0 4 0",
  moon: "M20 14.5A8.5 8.5 0 0 1 9.5 4 8.5 8.5 0 1 0 20 14.5Z",
  globe: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18ZM3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3Z",
  shield: "M12 3l7.5 3v5.5c0 4.6-3 8-7.5 9.5-4.5-1.5-7.5-4.9-7.5-9.5V6L12 3Z",
  help: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18ZM9.5 9.5a2.5 2.5 0 1 1 3.9 2.1c-.9.6-1.4 1.1-1.4 2.1M12 17h.01",
  doc: "M7 3h7l5 5v11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2ZM14 3v5h5M9 13h6M9 17h6",
  gem: "M7 4h10l4 5.5L12 21 3 9.5 7 4ZM3 9.5h18M9 9.5 12 21l3-11.5M9 9.5 11 4M15 9.5 13 4",
  copy: "M10 8h9a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1h-9a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1ZM5 15H4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1",
  share: "M12 15V4M8 7.5 12 4l4 3.5M5 12v7a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-7",
  external: "M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5",
  lock: "M7 11V8a5 5 0 0 1 10 0v3M6 11h12a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1v-8a1 1 0 0 1 1-1Z",
  alert: "M12 4 2.5 20h19L12 4ZM12 10v5M12 18h.01",
  users: "M9 5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7ZM2.5 20c.8-3.2 3.2-5 6.5-5s5.7 1.8 6.5 5M16 5.3a3.5 3.5 0 0 1 0 6.4M18 15.3c1.8.7 3 2.3 3.5 4.7",
  ticket: "M4 6h16a1 1 0 0 1 1 1v3a2 2 0 0 0 0 4v3a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-3a2 2 0 0 0 0-4V7a1 1 0 0 1 1-1ZM14 6v2M14 11v2M14 16v2",
  star: "M12 3.5l2.6 5.4 5.9.8-4.3 4.1 1 5.9-5.2-2.8-5.2 2.8 1-5.9-4.3-4.1 5.9-.8L12 3.5Z",
  car: "M5 11l1.7-4.7A2 2 0 0 1 8.6 5h6.8a2 2 0 0 1 1.9 1.3L19 11M4 11h16a1 1 0 0 1 1 1v5H3v-5a1 1 0 0 1 1-1ZM5 17v2M19 17v2M7 14h.01M17 14h.01",
  cap: "M2.5 10 12 5l9.5 5-9.5 5-9.5-5ZM6.5 12.5V17c3 2 8 2 11 0v-4.5M21.5 10v5",
  euro: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18ZM15.5 8.5a4 4 0 0 0-6.5 3.5 4 4 0 0 0 6.5 3.5M7.5 11h6M7.5 13h6",
  swap: "M4 8h14M14 4l4 4-4 4M20 16H6M10 12l-4 4 4 4",
  megaphone: "M4 10v4a1 1 0 0 0 1 1h3l9 4.5v-15L8 9H5a1 1 0 0 0-1 1ZM8 15l1.5 5h3L11 16.5M20 10.5a2 2 0 0 1 0 3",
  bolt: "M13 3 5 14h6l-1 7 8-11h-6l1-7Z",
  eye: "M2.5 12S6 5.5 12 5.5 21.500 12 21.500 12 18 18.500 12 18.500 2.500 12 2.500 12ZM12 9.500a2.500 2.500 0 1 0 0 5 2.500 2.500 0 0 0 0-5Z",
  chat: "M4 5h16a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H9l-5 4v-4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Z",
  bars: "M5 20v-7M12 20V5M19 20v-11",
  case: "M4 8h16a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1ZM9 8V6a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2M3 13h18M12 12v2",
  phone: "M8 3h8a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H8a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1ZM11 18h2",
  handshake: "M3 8l4-3 5 2 5-2 4 3v7l-4 1-5 4-5-4-4-1V8ZM12 7 8.500 11c1 1 2.200 1 3.500 0l1.500-1 4 4",
};
const AREA_ICONS = { lic: "id", veh: "car", mix: "car", cnj: "swap", exm: "cap", san: "euro", mat: "doc", rpc: "refresh", doc: "doc" };
const STATE_ICONS = { paused: "pause", booked: "check", locked: "lock", error: "alert", none: "x", pending: "clock" };
const TONES = { free: "ok", later: "warn", full: "bad", booked: "vio", locked: "warn", error: "warn" };
const STATE_KEYS = { free: "stFree", later: "stLater", full: "stFull", paused: "stPaused", booked: "stBooked", pending: "stPending", error: "stError", locked: "stLocked", none: "stNone" };

let me = null, L = T.ru, lang = "ru", tab = "home";
const stack = [];                      // открытые вложенные экраны
const sheets = [];                     // открытые нижние шторки
const scrolls = [];                    // где была прокрутка до перехода вглубь
const daySel = {};                     // выбранный день в календаре офиса
let cat = null, docs = null;           // справочник офисов и раздел «Документы»
const R = { office: null, cat: "lic", km: 100, job: null, ui: null, timer: 0, restored: false };

// ---------- мелкие помощники ----------

function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (k === "class") el.className = v;
    else if (k === "style") for (const [name, value] of Object.entries(v)) el.style.setProperty(name, value);
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined && v !== false) el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat(Infinity)) if (kid !== null && kid !== undefined && kid !== false) el.append(kid);
  return el;
}
function ico(name, size) {
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", "i");
  if (size) { svg.style.width = `${size}px`; svg.style.height = `${size}px`; }
  const path = document.createElementNS(NS, "path");
  path.setAttribute("d", ICONS[name] || ICONS.doc);
  svg.append(path);
  return svg;
}
const fill = (text, vars) => text.replace(/\{(\w+)\}/g, (_, k) => vars[k]);
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const plain = (text) => text.replace(/<[^>]+>/g, "").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#x27;/g, "'").replace(/&amp;/g, "&");
const tone = (state) => TONES[state] || "";
const haptic = (kind) => { try { tg.HapticFeedback.impactOccurred(kind || "light"); } catch (e) { /* не в Telegram */ } };
const success = () => { try { tg.HapticFeedback.notificationOccurred("success"); } catch (e) { /* не в Telegram */ } };
const iconOf = (s) => (s.state === "free" || s.state === "full" || s.state === "later" ? AREA_ICONS[s.icon] : STATE_ICONS[s.state] || AREA_ICONS[s.icon]) || "doc";

function date(iso, opts) {
  return new Intl.DateTimeFormat(LOCALES[lang], opts).format(new Date(iso + "T12:00:00"));
}
const fmtDate = (iso) => date(iso, { day: "numeric", month: "short" }).replace(".", "");
const fmtLong = (iso) => cap(date(iso, { weekday: "long", day: "numeric", month: "long" }));
function fmtUntil(ts) {
  return new Intl.DateTimeFormat(LOCALES[lang], { day: "numeric", month: "short" }).format(new Date(ts * 1000)).replace(".", "");
}

// Разметка Telegram из общих текстов бота: только разрешённые теги, остальное — обычный текст
function rich(html) {
  const box = h("div", { class: "rich" });
  const open = [box];
  html.split(/(<\/?(?:blockquote|code|b|i)(?:\s[^>]*)?>)/).forEach((part) => {
    const tag = /^<(\/?)(blockquote|code|b|i)[\s>]/.exec(part);
    if (!tag) { if (part) open[open.length - 1].append(plain(part)); return; }
    if (tag[1]) { if (open.length > 1) open.pop(); return; }
    const el = document.createElement(tag[2]);
    open[open.length - 1].append(el);
    open.push(el);
  });
  return box;
}

function toast(text, kind) {
  const old = layer.querySelector(".toast");
  if (old) old.remove();
  const el = h("div", { class: "toast " + (kind || "") }, plain(text));
  layer.append(el);
  setTimeout(() => { el.classList.add("out"); setTimeout(() => el.remove(), 260); }, 3000);
}

async function api(path, body) {
  const res = await fetch("/api/" + path, {
    method: body ? "POST" : "GET",
    headers: { "X-Init-Data": initData, "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 402) load();
    const err = new Error(data.error || data.status || res.status);
    err.code = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

function openLink(url) { if (tg && tg.openLink) tg.openLink(url); else window.open(url, "_blank", "noopener"); }
function openTg(url) { if (tg && tg.openTelegramLink) tg.openTelegramLink(url); else openLink(url); }
function openAny(url) { if (/^https:\/\/t\.me\//.test(url)) openTg(url); else openLink(url); }
function openBot() { openTg(`https://t.me/${me.bot}`); if (tg) tg.close(); }

// ---------- навигация ----------

function render(motion) {
  if (!me) return;
  stopTick();
  const wide = !me.premium;
  if (wide) stack.length = 0;
  const top = stack[stack.length - 1];
  const nodes = top ? top() : wide ? lockedScreen() : SCREENS[tab]();
  const y = window.scrollY;
  root.replaceChildren(h("div", { class: "view " + (motion || "") }, nodes));
  syncChrome();
  if (motion === "pop") window.scrollTo(0, scrolls.pop() || 0);
  else if (motion) window.scrollTo(0, 0);
  else window.scrollTo(0, y);
}
function push(screen) { scrolls.push(window.scrollY); stack.push(screen); haptic(); render("push"); }
function pop() { stack.pop(); haptic(); render("pop"); }
function setTab(id) {
  if (id === tab && !stack.length) return;
  tab = id; stack.length = 0; scrolls.length = 0;
  haptic();
  render("fade");
}
function syncChrome() {
  const showTabs = me && me.premium && !stack.length;
  tabbar.hidden = !showTabs;
  if (showTabs) tabbar.style.setProperty("--i", TABS.indexOf(tab));
  [...tabbar.querySelectorAll("button")].forEach((b) => b.classList.toggle("on", b.dataset.tab === tab));
  if (tg && tg.BackButton) { if (stack.length || sheets.length) tg.BackButton.show(); else tg.BackButton.hide(); }
}
function onBack() {
  if (sheets.length) sheets[sheets.length - 1]();
  else if (stack.length) pop();
}
function buildTabs() {
  const labels = { home: L.tabHome, radar: L.tabRadar, docs: L.tabDocs, bonus: L.tabBonus, profile: L.tabProfile };
  tabbar.replaceChildren(h("i", { class: "glider" }), ...TABS.map((id) =>
    h("button", { "data-tab": id, onclick: () => setTab(id) }, ico(TAB_ICONS[id]), h("span", {}, labels[id]))));
}

function sheet(title, build) {
  const close = () => {
    const at = sheets.indexOf(close);
    if (at >= 0) sheets.splice(at, 1);
    wrap.classList.add("out");
    setTimeout(() => wrap.remove(), 220);
    syncChrome();
  };
  const body = h("div", { class: "sheet-body" });
  const panel = h("div", { class: "sheet" }, h("i", { class: "grip" }),
    title ? h("div", { class: "sheet-head" }, h("h2", {}, title), h("button", { class: "round", "aria-label": "×", onclick: close }, ico("x", 18))) : null, body);
  const wrap = h("div", { class: "sheet-wrap" }, h("div", { class: "shade", onclick: close }), panel);
  layer.append(wrap);
  sheets.push(close);
  syncChrome();
  haptic();
  build(body, close);
  return close;
}
function closeSheets() { while (sheets.length) sheets[sheets.length - 1](); }

function confirmSheet(title, text, yes, danger, run) {
  sheet(null, (body, close) => {
    body.append(h("div", { class: "confirm" }, h("h2", {}, title), text ? h("p", {}, text) : null,
      h("button", { class: "btn " + (danger ? "danger-solid" : ""), onclick: () => { close(); run(); } }, yes),
      h("button", { class: "btn quiet", onclick: close }, L.cancel)));
  });
}

function picker(title, items, opts) {
  const { search, onPick } = opts || {};
  sheet(title, (body, close) => {
    const list = h("div", { class: "pick-list" });
    const fold = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
    const draw = (rows, q) => {
      const shown = rows.filter((o) => fold(o.label).includes(fold(q)));
      list.replaceChildren(...(shown.length ? shown.map((o) =>
        h("button", { class: "pick", onclick: () => onPick(o, close) },
          o.icon ? h("span", { class: "tile sm" }, ico(o.icon, 20)) : null,
          h("span", { class: "main" }, h("b", {}, o.label), o.sub ? h("small", {}, o.sub) : null),
          ico(o.mark || "right", 18)))
        : [h("div", { class: "blank" }, L.nothing)]));
    };
    if (search) body.append(h("label", { class: "search" }, ico("search", 18), h("input", { placeholder: L.search, autocomplete: "off", oninput: (e) => draw(items, e.target.value) })));
    body.append(list);
    if (items.then) {
      list.append(h("div", { class: "blank" }, h("span", { class: "spin" })));
      items.then((rows) => { items = rows; draw(rows, ""); }).catch((e) => { close(); toast(e.code === 503 ? L.siteDown : L.failed, "bad"); });
    } else draw(items, "");
  });
}

// ---------- данные ----------

async function load(motion) {
  me = await api("me");
  const preferred = tg && tg.initDataUnsafe && tg.initDataUnsafe.user && tg.initDataUnsafe.user.language_code;
  lang = me.langSet ? me.lang : T[preferred] ? preferred : "en";
  L = T[lang];
  document.documentElement.lang = lang;
  buildTabs();
  render(motion);
}

async function refresh() {  // тихое обновление: бот мог найти новые даты, пока приложение открыто
  if (document.hidden || sheets.length || !me || document.activeElement.tagName === "INPUT") return;
  const fresh = await api("me").catch(() => null);
  if (!fresh) return;
  const same = (a, b) => JSON.stringify({ ...a, nextCheck: 0 }) === JSON.stringify({ ...b, nextCheck: 0 });
  const changed = !same(fresh, me);
  me = fresh;
  if (changed && !(tab === "radar" || tab === "docs")) render();
}

async function act(fn, done) {
  try {
    await fn();
    haptic("medium");
    await load();
    if (done) done();
  } catch (e) {
    toast(e.code === 409 ? L.limit : e.code === 429 ? L.wait : L.failed, "bad");
  }
}

async function catalog() {
  if (!cat) cat = await api("offices");
  return cat;
}

// ---------- общие блоки ----------

function langChip() {
  return h("button", { class: "lang-chip", "aria-label": L.language, onclick: langSheet }, ico("globe", 16), lang.toUpperCase());
}
function langSheet() {
  sheet(L.language, (body, close) => body.append(langGrid(close)));
}
function langGrid(close) {
  return h("div", { class: "lang-grid" }, Object.entries(LANG_NAMES).map(([code, name]) =>
    h("button", { class: "lang" + (code === lang ? " on" : ""), onclick: () => setLang(code, close) },
      h("span", { class: "code" }, code.toUpperCase()), h("b", {}, name), code === lang ? ico("check", 18) : null)));
}
async function setLang(code, close) {
  if (close) close();
  if (code === lang && me.langSet) return;
  try {
    await api("lang", { lang: code });
    cat = null; docs = null;
    await load("fade");
    success();
  } catch (e) { toast(L.failed, "bad"); }
}
function notice(text) { return h("div", { class: "notice" }, ico("alert", 18), h("span", {}, text)); }
function sectionHead(title, aside) { return h("div", { class: "section" }, h("h2", {}, title), aside || null); }
function stat(value, label) { return h("div", { class: "stat" }, h("b", {}, String(value)), h("span", {}, label)); }
function emptyBox(icon, title, text, action) {
  return h("div", { class: "empty" }, h("div", { class: "orb" }, icon), title ? h("h3", {}, title) : null, text ? h("p", {}, text) : null, action || null);
}
function row(icon, title, sub, onclick, aside) {
  return h("button", { class: "row", onclick }, h("span", { class: "tile sm" }, ico(icon, 20)),
    h("span", { class: "main" }, h("b", {}, title), sub ? h("small", {}, sub) : null), aside || ico("right", 18));
}
function toggle(icon, title, sub, on, onchange) {
  const box = h("button", { class: "switch" + (on ? " on" : ""), role: "switch", "aria-checked": on ? "true" : "false", "aria-label": title }, h("i"));
  const el = h("div", { class: "row static" }, h("span", { class: "tile sm" }, ico(icon, 20)), h("span", { class: "main" }, h("b", {}, title), h("small", {}, sub)), box);
  box.addEventListener("click", () => { box.classList.toggle("on"); haptic(); onchange(box.classList.contains("on")); });
  return el;
}

// ---------- главная ----------

const minutesLeft = () => (me.nextCheck ? Math.max(0, Math.ceil((me.nextCheck * 1000 - Date.now()) / 60000)) : null);
function nextText() {
  if (me.checksPaused) return L.stopped;
  const mins = minutesLeft();
  return mins === null ? "—" : mins === 0 ? L.now : fill(L.inMin, { n: mins });
}
function ring() {
  const circle = (cls) => { const c = document.createElementNS(NS, "circle"); c.setAttribute("cx", "36"); c.setAttribute("cy", "36"); c.setAttribute("r", "30"); c.setAttribute("class", cls); return c; };
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 72 72");
  const track = circle("ring-track"), bar = circle("ring-bar");
  const size = 2 * Math.PI * 30;
  bar.setAttribute("stroke-dasharray", size.toFixed(1));
  svg.append(track, bar);
  const label = h("b", {}), box = h("div", { class: "ring" }, svg, label);
  const paint = () => {
    const mins = minutesLeft();
    label.textContent = mins === null || me.checksPaused ? "—" : String(mins);
    bar.setAttribute("stroke-dashoffset", (size * (mins === null ? 1 : Math.min(1, mins / me.top.interval))).toFixed(1));
  };
  paint();
  return { box, paint };
}
let tickTimer = 0;
function stopTick() { clearInterval(tickTimer); }

function planLine() {
  return me.premiumUntil * 1000 > Date.now() ? fill(L.planUntil, { date: fmtUntil(me.premiumUntil) }) : L.planForever;
}
function hero() {
  const r = ring();
  const next = h("strong", {}, nextText());
  const freeCount = me.subs.filter((s) => s.state === "free").length;
  tickTimer = setInterval(() => { r.paint(); next.textContent = nextText(); }, 15000);
  return h("section", { class: "hero brand" }, h("i", { class: "glow" }),
    h("div", { class: "hero-top" },
      h("div", { class: "logo" }, h("img", { src: "/app/mark.svg", alt: "" })),
      h("div", { class: "hero-name" }, h("h1", {}, "OkSita"), h("small", {}, h("i", { class: "live" }), planLine())),
      langChip()),
    h("div", { class: "hero-check" }, r.box, h("div", {}, h("span", {}, L.nextCheck), next, h("small", {}, ico("bolt", 13), fill(L.everyMin, { n: me.top.interval })))),
    h("div", { class: "stats" }, stat(`${me.used}/${me.limit}`, L.statOffices), stat(freeCount, L.statFree), stat(me.alerts, L.statAlerts)));
}
function strip(s) {
  if (!s.days.length || s.booked) return null;
  const loads = new Map(s.days), base = new Date();
  const cells = [];
  for (let i = 0; i < 28; i++) {
    const d = new Date(base.getFullYear(), base.getMonth(), base.getDate() + i, 12);
    const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    cells.push(h("i", { class: loads.get(iso) || "" }));
  }
  return h("div", { class: "strip" }, cells);
}
function officeCard(s) {
  const when = s.booked ? fmtDate(s.booked) : s.nearest ? fmtDate(s.nearest) : L[STATE_KEYS[s.state]];
  return h("button", { class: "office", onclick: () => push(() => officeScreen(s.id)) },
    h("div", { class: "office-row" }, h("span", { class: "tile " + tone(s.state) }, ico(iconOf(s), 22)),
      h("span", { class: "main" }, h("b", {}, s.city), h("small", {}, s.hint ? cap(s.hint) : s.type)),
      h("span", { class: "pill " + tone(s.state) }, when), ico("right", 16)),
    strip(s));
}
function spotlight(s) {
  return h("section", { class: "spot" },
    h("div", { class: "spot-top" }, h("span", {}, L.spotlight), h("span", { class: "pulse" }, s.city)),
    h("strong", {}, fmtLong(s.nearest)),
    h("div", { class: "spot-actions" },
      h("button", { class: "btn white", onclick: () => openLink(me.bookUrl) }, L.bookNow, ico("external", 16)),
      h("button", { class: "btn glass", "aria-label": L.details, onclick: () => push(() => officeScreen(s.id)) }, ico("right", 18))));
}
function trialLeft() {
  const days = Math.ceil((me.premiumUntil * 1000 - Date.now()) / 86400000);
  return days <= 1 ? L.trialLastDay : fill(L.trialLeftDays, { n: days });
}
function trialStrip() {
  if (!me.inTrial) return null;
  return h("button", { class: "trial-strip", onclick: () => setTab("profile") },
    h("span", { class: "tile sm vio" }, ico("gift", 20)),
    h("span", { class: "main" }, h("b", {}, fill(L.trialBanner, { left: trialLeft() })), h("small", {}, L.trialHint)),
    h("span", { class: "mini solid" }, L.trialBuy));
}
function homeScreen() {
  const best = me.subs.filter((s) => s.state === "free").sort((a, b) => a.nearest.localeCompare(b.nearest))[0];
  const addBtn = h("button", { class: "add", disabled: me.used >= me.limit, onclick: addOffice }, ico("plus", 16), L.add);
  return [hero(), me.outage ? notice(L.outage) : null, trialStrip(), best ? spotlight(best) : null,
    sectionHead(L.myOffices, addBtn),
    me.subs.length ? h("div", { class: "list" }, me.subs.map(officeCard))
      : emptyBox(h("img", { src: "/app/mark.svg", alt: "" }), L.emptyTitle, L.emptyText, h("button", { class: "btn", onclick: addOffice }, ico("plus", 18), L.addOffice))];
}

// ---------- добавление офиса ----------

async function addOffice() {
  if (me.used >= me.limit) return toast(L.limit, "bad");
  picker(L.pickOffice, catalog().then((c) => c.offices.map((o) => ({ id: o.id, label: o.city, icon: "pin" }))), {
    search: true,
    onPick: (office) => picker(`${office.label}: ${L.pickType.toLowerCase()}`, api(`areas?office=${encodeURIComponent(office.id)}`).then((d) =>
      d.areas.map((a) => ({ id: a.code, label: a.label, sub: a.hint ? cap(a.hint) : "", icon: AREA_ICONS[a.icon] || "doc" }))), {
      onPick: (area) => addSub(office.id, area.id),
    }),
  });
}
async function addSub(centro, area) {
  try {
    const { status } = await api("subs", { centro, area });
    closeSheets();
    success();
    stack.length = 0;
    tab = "home";
    await load("fade");
    toast(status === "exists" ? L.exists : L.added, "ok");
  } catch (e) {
    toast(e.data && e.data.status === "full" ? L.botFull : e.code === 409 ? L.limit : L.failed, "bad");
  }
}

// ---------- офис ----------

function calendarCard(s, onPick) {
  const loads = new Map(s.days), visible = new Set(s.visible);
  const months = [...new Set(s.days.map((d) => d[0].slice(0, 7)))].sort();
  const wrap = h("section", { class: "card" });
  if (!months.length) { wrap.append(h("h3", {}, L.calendar), h("div", { class: "blank" }, L.noDates)); return wrap; }
  let idx = Math.max(0, months.indexOf((daySel[s.id] || months[0]).slice(0, 7)));
  const week = [...Array(7)].map((_, i) => cap(date(`2024-01-0${i + 1}`, { weekday: "short" })).replace(".", "").slice(0, 2));
  const draw = () => {
    const [y, m] = months[idx].split("-").map(Number);
    const first = (new Date(y, m - 1, 1).getDay() + 6) % 7, total = new Date(y, m, 0).getDate();
    const cells = week.map((w) => h("span", { class: "wd" }, w));
    for (let i = 0; i < first; i++) cells.push(h("i"));
    for (let d = 1; d <= total; d++) {
      const iso = `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      const load = loads.get(iso);
      cells.push(load
        ? h("button", { class: `day ${load}${visible.has(iso) ? "" : " dim"}${daySel[s.id] === iso ? " sel" : ""}`, onclick: () => { daySel[s.id] = iso; haptic(); draw(); onPick(iso); } }, String(d))
        : h("span", { class: "day" }, String(d)));
    }
    const stepper = (dir, icon) => (months.length > 1 ? h("button", { class: "round", "aria-label": icon, onclick: () => { idx = (idx + dir + months.length) % months.length; haptic(); draw(); } }, ico(icon, 18)) : h("i"));
    wrap.replaceChildren(
      h("div", { class: "cal-head" }, stepper(-1, "left"), h("b", {}, `${cap(date(`${months[idx]}-15`, { month: "long" }))} ${y}`), stepper(1, "right")),
      h("div", { class: "cal" }, cells),
      h("div", { class: "legend" }, [["many", L.many], ["mid", L.mid], ["few", L.few]].map(([c, t]) => h("span", {}, h("i", { class: c }), t))));
  };
  draw();
  return wrap;
}
function hoursCard(s) {
  const box = h("section", { class: "card nearest" });
  const draw = (iso) => {
    const hours = s.hoursBy[iso] || [];
    box.replaceChildren(h("h3", {}, iso === s.nearest ? L.spotlight : L.bookDate), h("strong", {}, fmtLong(iso)),
      ...(hours.length ? [h("span", { class: "label" }, L.freeHours), h("div", { class: "hours" }, hours.slice(0, 18).map((t) => h("span", {}, t)))]
        : [h("p", { class: "muted" }, L.hoursOnSite)]));
  };
  return { box, draw };
}
function officeHeader(s) {
  return h("section", { class: `hero office-head ${s.state}` }, h("i", { class: "glow" }),
    h("div", { class: "hero-top" }, h("span", { class: "tile glass" }, ico(iconOf(s), 24)),
      h("div", { class: "hero-name" }, h("h1", {}, s.city), h("small", {}, s.type))),
    h("div", { class: "head-status" }, h("span", { class: "badge-glass" }, s.statusText)),
    s.address || s.schedule ? h("div", { class: "facts" },
      s.address ? h("span", {}, ico("pin", 15), s.address) : null, s.schedule ? h("span", {}, ico("clock", 15), s.schedule) : null) : null);
}
function historyCard(id) {
  const box = h("section", { class: "card" }, h("h3", {}, L.history), h("div", { class: "line-skeleton" }), h("div", { class: "line-skeleton short" }));
  api(`subs/${id}/history`).then(({ events, bestHour, average, hours }) => {
    box.replaceChildren(h("h3", {}, L.history));
    if (!events.length) return box.append(h("p", { class: "muted" }, L.noHistory));
    if (hours) box.append(h("span", { class: "label" }, L.hoursChart), hoursChart(hours));
    box.append(h("div", { class: "timeline" }, events.map((e) => h("div", { class: "tl" + (e.lasted ? "" : " open") }, h("i"),
      h("b", {}, cap(e.at)), h("small", {}, `${e.lasted ? fill(L.lasted, { t: e.lasted }) : L.historyOpen} · ${e.days}`)))));
    const facts = [bestHour !== null ? fill(L.bestHour, { h: bestHour }) : null, average ? fill(L.avgLast, { t: average }) : null].filter(Boolean);
    if (facts.length) box.append(h("div", { class: "hints" }, facts.map((f) => h("span", {}, f))));
  }).catch(() => box.remove());
  return box;
}
function officeScreen(id) {
  const s = me.subs.find((x) => x.id === id);
  if (!s) { stack.pop(); return homeScreen(); }
  if (s.booked) return bookedScreen(s);
  if (!daySel[id] || !s.days.some((d) => d[0] === daySel[id])) daySel[id] = s.nearest || (s.days[0] && s.days[0][0]) || null;
  const hours = s.days.length ? hoursCard(s) : null;
  if (hours) hours.draw(daySel[id]);
  const tile = (icon, label, onclick, cls) => h("button", { class: "tool " + (cls || ""), onclick }, h("span", {}, ico(icon, 20)), label);
  const filter = [0, 7, 14, 30, 60].map((v) => h("button", {
    class: "chip" + (s.filter === v ? " on" : ""), onclick: () => act(() => api(`subs/${id}/filter`, { days: v }), () => render()),
  }, v ? fill(L.filterDays, { n: v }) : L.filterAny));
  return [
    officeHeader(s),
    s.checked ? h("p", { class: "checked" }, fill(L.checkedAt, { when: s.checked })) : null,
    me.outage ? notice(L.outage) : null,
    s.note ? h("section", { class: "card" }, rich(s.note)) : null,
    hours ? hours.box : null,
    s.state === "locked" ? null : calendarCard(s, (iso) => hours && hours.draw(iso)),
    h("div", { class: "cta" },
      h("button", { class: "btn", onclick: () => openLink(me.bookUrl) }, L.bookNow, ico("external", 17)),
      s.days.length ? h("button", { class: "btn success", onclick: () => bookSheet(s) }, ico("check", 18), L.iBooked) : null),
    h("div", { class: "tools" },
      tile("refresh", L.actCheck, () => checkNow(id)),
      tile(s.paused ? "play" : "pause", s.paused ? L.actResume : L.actPause, () => act(() => api(`subs/${id}/pause`, { paused: !s.paused }), () => render())),
      tile("radar", L.actRadar, () => { R.office = { id: s.centro, city: s.city }; R.job = null; setTab("radar"); }),
      tile("trash", L.actRemove, () => removeSub(id), "danger")),
    s.state === "locked" ? null : h("section", { class: "card" }, h("h3", {}, L.filterTitle), h("div", { class: "chips" }, filter), h("p", { class: "muted small" }, L.filterHint)),
    s.state === "locked" ? null : historyCard(id),
  ];
}
function bookedScreen(s) {
  return [
    officeHeader(s),
    h("section", { class: "hero visit" }, h("i", { class: "glow" }),
      h("span", { class: "eyebrow" }, s.past ? L.visitPast : L.visit), h("strong", {}, cap(s.bookedLabel)),
      s.past ? null : h("p", {}, ico("bell", 15), L.remind)),
    s.past ? null : h("section", { class: "card" }, h("h3", {}, L.bring),
      h("div", { class: "checklist" }, s.checklist.map((item) => h("span", {}, ico("check", 16), item))), h("p", { class: "muted small" }, L.bringNote)),
    h("div", { class: "cta" },
      h("button", { class: "btn quiet", onclick: () => unbook(s.id) }, ico("refresh", 18), L.rebook),
      h("button", { class: "btn danger", onclick: () => removeSub(s.id) }, ico("trash", 18), L.actRemove)),
  ];
}
async function unbook(id) {
  try {
    const { resumed } = await api(`subs/${id}/unbook`, {});
    await load();
    toast(resumed ? L.rebooked : L.rebookedPaused, resumed ? "ok" : "");
  } catch (e) { toast(L.failed, "bad"); }
}
function removeSub(id) {
  confirmSheet(L.confirmRemove, L.confirmRemoveText, L.actRemove, true, async () => {
    try {
      await api(`subs/${id}/delete`, {});
      stack.length = 0;
      await load("pop");
    } catch (e) { toast(L.failed, "bad"); }
  });
}
async function checkNow(id) {
  try { await api(`subs/${id}/check`, {}); haptic("medium"); toast(L.checkStarted, "ok"); }
  catch (e) { toast(e.code === 429 ? L.wait : e.code === 503 ? L.siteDown : L.failed, "bad"); }
}
function bookSheet(s) {
  let day = daySel[s.id] || s.nearest, time = null;
  sheet(L.bookTitle, (body, close) => {
    const hoursBox = h("div", { class: "chips" });
    const drawHours = () => hoursBox.replaceChildren(
      ...(s.hoursBy[day] || []).slice(0, 16).map((t) => h("button", { class: "chip" + (time === t ? " on" : ""), onclick: () => { time = t; haptic(); drawHours(); custom.value = t; } }, t)));
    const custom = h("input", { class: "field", type: "time", onchange: (e) => { time = e.target.value || null; drawHours(); } });
    const dates = h("div", { class: "chips" });
    const other = h("input", { class: "field", type: "date", min: new Date().toISOString().slice(0, 10), onchange: (e) => { if (e.target.value) { day = e.target.value; drawDays(); drawHours(); } } });
    const drawDays = () => dates.replaceChildren(...s.days.slice(0, 8).map(([iso]) =>
      h("button", { class: "chip" + (day === iso ? " on" : ""), onclick: () => { day = iso; time = null; haptic(); other.value = ""; drawDays(); drawHours(); } }, fmtDate(iso))));
    drawDays(); drawHours();
    body.append(h("span", { class: "label" }, L.bookDate), dates, h("span", { class: "label" }, L.otherDate), other,
      h("span", { class: "label" }, L.bookTime), hoursBox, custom,
      h("button", { class: "btn success", onclick: async () => {
        try {
          await api(`subs/${s.id}/book`, { date: day, time });
          close(); success(); await load(); toast(L.bookSaved, "ok");
        } catch (e) { toast(L.failed, "bad"); }
      } }, ico("check", 18), L.save));
  });
}

// ---------- радар ----------

function radarHero(running) {
  return h("section", { class: "hero night" + (running ? " active" : "") }, h("div", { class: "scope" }, h("i", { class: "sweep" }), h("i", { class: "blip a" }), h("i", { class: "blip b" }), h("i", { class: "blip c" })),
    h("div", { class: "hero-copy" }, h("h1", {}, L.radarTitle), h("p", {}, L.radarText)));
}
function radarScreen() {
  if (!R.office && me.subs[0]) R.office = { id: me.subs[0].centro, city: me.subs[0].city };
  if (!R.restored) { R.restored = true; pollRadar(true); }
  if (!cat) catalog().then(() => tab === "radar" && !stack.length && render()).catch(() => {});
  if (R.job && R.job.state === "running") return radarRunning();
  if (R.job && R.job.state === "done") return radarResults();
  const cats = cat ? cat.cats : [];
  return [
    radarHero(false),
    me.outage ? notice(L.outage) : null,
    row("pin", R.office ? R.office.city : L.choose, L.radarFrom, pickRadarOffice),
    row("bars", L.statsTitle, L.statsSub, () => push(statsScreen)),
    h("section", { class: "card" }, h("h3", {}, L.radarType), h("div", { class: "chips" }, cats.map((c) =>
      h("button", { class: "chip" + (R.cat === c.id ? " on" : ""), onclick: () => { R.cat = c.id; haptic(); render(); } }, c.label)))),
    h("section", { class: "card" }, h("h3", {}, L.radarRange), h("div", { class: "segment" }, [100, 150, 250].map((km) =>
      h("button", { class: R.km === km ? "on" : "", onclick: () => { R.km = km; haptic(); render(); } }, fill(L.km, { n: km }))))),
    h("button", { class: "btn", disabled: !R.office, onclick: startRadar }, ico("radar", 19), L.radarStart),
  ];
}
function pickRadarOffice() {
  picker(L.radarFrom, catalog().then((c) => c.offices.map((o) => ({ id: o.id, label: o.city, icon: "pin" }))), {
    search: true, onPick: (o, close) => { R.office = { id: o.id, city: o.label }; close(); render(); },
  });
}
async function startRadar() {
  try {
    await api("radar", { centro: R.office.id, cat: R.cat, km: R.km });
    R.job = { state: "running", done: 0, total: 0, current: R.office.city };
    haptic("medium");
    render("fade");
    pollRadar();
  } catch (e) { toast(e.data && e.data.text ? e.data.text : L.failed, "bad"); }
}
function radarRunning() {
  const j = R.job;
  const label = h("b", {}, fill(L.radarNow, { city: j.current || "…" }));
  const step = h("span", {}, fill(L.radarStep, { done: j.done, total: j.total || "…" }));
  const bar = h("i", { style: { width: `${j.total ? (j.done / j.total) * 100 : 6}%` } });
  R.ui = { label, step, bar };
  return [radarHero(true), h("section", { class: "card progress" }, h("h3", {}, L.radarRunning), label, h("div", { class: "bar" }, bar), step)];
}
function paintRadar() {
  const { ui, job } = R;
  if (!ui || !job) return;
  ui.label.textContent = fill(L.radarNow, { city: job.current || "…" });
  ui.step.textContent = fill(L.radarStep, { done: job.done, total: job.total || "…" });
  ui.bar.style.width = `${job.total ? Math.max(6, (job.done / job.total) * 100) : 6}%`;
}
async function pollRadar(once) {
  clearTimeout(R.timer);
  try {
    const job = await api("radar");
    const was = R.job && R.job.state;
    R.job = job.state === "idle" ? null : job;
    if (job.state === "running") { paintRadar(); R.timer = setTimeout(pollRadar, 2500); if (once && tab === "radar") render(); return; }
    if (job.state === "failed") toast(job.text, "bad");
    if (job.state === "failed") R.job = null;
    if (was === "running" && tab === "radar" && !stack.length) { success(); render("fade"); }
    else if (once && job.state === "done" && tab === "radar" && !stack.length) render();
  } catch (e) { if (R.job && R.job.state === "running") R.timer = setTimeout(pollRadar, 4000); }
}
function radarItem(item, rank) {
  const notes = { none: L.rNone, full: L.stFull, error: L.rError, locked: L.rLocked };
  const trackBtn = item.code && !item.tracked ? h("button", { class: "mini", onclick: () => trackFromRadar(item) }, ico("bell", 15), L.track)
    : item.tracked ? h("span", { class: "pill ok" }, L.tracked) : null;
  return h("div", { class: "rank " + item.state },
    h("span", { class: "place" + (item.state === "free" && rank < 3 ? ` p${rank}` : "") }, item.state === "free" ? String(rank + 1) : ico(item.state === "full" ? "x" : item.state === "locked" ? "lock" : "alert", 16)),
    h("span", { class: "main" }, h("b", {}, item.city), h("small", {}, [item.km ? fill(L.km, { n: item.km }) : null,
      item.state === "free" ? `${fill(L.fromDate, { date: fmtDate(item.nearest) })} · ${fill(L.daysN, { n: item.days })}` : notes[item.state]].filter(Boolean).join(" · "))),
    trackBtn);
}
async function trackFromRadar(item) {
  try {
    await api("subs", { centro: item.centro, area: item.code });
    item.tracked = true;
    success();
    await load();
  } catch (e) { toast(e.data && e.data.status === "full" ? L.botFull : e.code === 409 ? L.limit : L.failed, "bad"); }
}
function radarResults() {
  const items = R.job.items;
  const free = items.filter((i) => i.state === "free");
  return [
    radarHero(false),
    sectionHead(L.radarResults, h("button", { class: "add", onclick: () => { R.job = null; render("fade"); } }, ico("refresh", 15), L.radarNew)),
    free.length ? h("button", { class: "btn", onclick: () => openLink(me.bookUrl) }, L.bookNow, ico("external", 17)) : notice(L.radarEmpty),
    h("div", { class: "list" }, items.map((item, i) => radarItem(item, free.indexOf(item) >= 0 ? free.indexOf(item) : i))),
    h("p", { class: "muted small center" }, L.radarNote),
  ];
}

// ---------- документы ----------

async function loadDocs() {
  try { docs = await api("docs"); if (tab === "docs" && !stack.length) render(); }
  catch (e) { toast(L.failed, "bad"); }
}
function pickSignal(onDone) {
  picker(L.pickProvince, docs.provinces.map((p) => ({ id: p.id, label: p.name })), {
    search: true,
    onPick: (province) => picker(`${province.label}: ${L.pickDoc.toLowerCase()}`, docs.docs.map((d) => ({ id: d.id, label: d.title, icon: "id" })), {
      onPick: (doc) => onDone(province, doc),
    }),
  });
}
function reportSignal() {
  pickSignal((province, doc) => confirmSheet(L.seeConfirm, `${doc.label} · ${province.label}. ${L.seeConfirmText}`, L.seeYes, false, async () => {
    try {
      const { text, status } = await api("docs/report", { province: province.id, doc: doc.id });
      closeSheets();
      if (status === "ok" || status === "merged") success();
      toast(text, status === "muted" ? "bad" : "ok");
    } catch (e) { toast(L.failed, "bad"); }
  }));
}
function addSignal() {
  pickSignal(async (province, doc) => {
    try {
      const { text } = await api("docs/sub", { province: province.id, doc: doc.id });
      closeSheets(); success(); toast(text, "ok");
      await loadDocs();
    } catch (e) { toast(e.data && e.data.text ? e.data.text : L.failed, "bad"); }
  });
}
function docsScreen() {
  const head = h("section", { class: "hero ocean" }, h("i", { class: "glow" }),
    h("div", { class: "hero-copy" }, h("h1", {}, L.docsTitle), h("p", {}, L.docsText)));
  if (!docs) { loadDocs(); return [head, h("div", { class: "skeleton" }), h("div", { class: "skeleton short" })]; }
  const count = `${docs.mine.length}/${docs.limit}`;
  head.append(h("button", { class: "btn white", onclick: reportSignal }, ico("eye", 19), L.iSee));
  return [
    head,
    sectionHead(L.mySignals, h("span", { class: "counter" }, count)),
    docs.mine.length ? h("div", { class: "list" }, docs.mine.map((m) =>
      h("div", { class: "row static" }, h("span", { class: "tile sm ok" }, ico("bell", 20)),
        h("span", { class: "main" }, h("b", {}, m.title), h("small", {}, [m.name, m.hour !== null ? fill(L.bestAround, { h: m.hour }) : null].filter(Boolean).join(" · "))),
        h("button", { class: "round", "aria-label": L.actRemove, onclick: () => removeSignal(m) }, ico("trash", 17)))))
      : emptyBox(ico("bell", 28), null, L.noSignals),
    h("button", { class: "btn quiet", disabled: docs.mine.length >= docs.limit, onclick: addSignal }, ico("plus", 18), L.addSignal),
    h("section", { class: "card" }, h("h3", {}, `${L.windowsTitle} · ${docs.windows.mine.length}/${docs.windows.limit}`),
      h("div", { class: "chips" }, docs.windows.options.map((hour) => h("button", {
        class: "chip" + (docs.windows.mine.includes(hour) ? " on" : ""), onclick: () => toggleWindow(hour),
      }, `${String(hour).padStart(2, "0")}:00`))), h("p", { class: "muted small" }, L.windowsHint)),
    h("div", { class: "group" },
      row("doc", L.guideTitle, null, () => push(textPage("tie", L.guideTitle))),
      row("external", L.docsSite, null, () => openLink(docs.site))),
    h("p", { class: "muted small center" }, L.docsWarn),
  ];
}
async function toggleWindow(hour) {
  try {
    const { mine } = await api("docs/windows", { hour });
    docs.windows.mine = mine;
    haptic();
    render();
  } catch (e) { toast(e.data && e.data.text ? e.data.text : L.failed, "bad"); }
}
async function removeSignal(m) {
  try { await api("docs/unsub", { province: m.province, doc: m.doc }); haptic("medium"); await loadDocs(); }
  catch (e) { toast(L.failed, "bad"); }
}

// ---------- бонусы ----------

function taskRow(t) {
  const reward = h("span", { class: "reward" }, `+${t.reward}`);
  const mark = h("span", { class: "tick" + (t.done ? " on" : "") }, t.done ? ico("check", 16) : null);
  let action = null;
  if (!t.done && t.id) {
    action = h("div", { class: "task-actions" },
      h("button", { class: "mini", onclick: () => openAny(t.url) }, L.taskGo),
      h("button", { class: "mini solid", onclick: () => checkTask(t.id) }, L.taskCheck));
  } else if (!t.done && t.key === "b:ads") {
    action = h("div", { class: "task-actions" }, h("button", { class: "mini solid", onclick: () => saveSetting({ ads: true }) }, L.enable));
  }
  return h("div", { class: "task" + (t.done ? " done" : "") }, h("div", { class: "task-row" }, mark, h("span", { class: "main" }, t.title), reward), action);
}
async function checkTask(id) {
  try {
    const { status, text } = await api(`tasks/${id}/check`, {});
    if (status === "ok") { success(); await load(); }
    toast(text, status === "ok" ? "ok" : "");
  } catch (e) { toast(L.failed, "bad"); }
}
async function collect() {
  try {
    const { status, text } = await api("bonus/collect", {});
    if (status === "ok") success();
    await load();
    toast(text, status === "ok" ? "ok" : "");
  } catch (e) { toast(L.failed, "bad"); }
}
function promoBox() {
  const input = h("input", { class: "field", placeholder: L.promoPh, maxlength: "32", autocapitalize: "characters", autocomplete: "off", spellcheck: "false" });
  const apply = async () => {
    const code = input.value.trim();
    if (!code) return;
    try {
      const { status, text } = await api("promo", { code });
      if (status === "ok") { success(); input.value = ""; await load(); }
      toast(text, status === "ok" ? "ok" : "bad");
    } catch (e) { toast(L.failed, "bad"); }
  };
  return h("div", { class: "inline" }, input, h("button", { class: "btn compact", onclick: apply }, L.apply));
}
function bonusScreen() {
  const share = () => openTg(`https://t.me/share/url?url=${encodeURIComponent(me.refLink)}&text=${encodeURIComponent(me.shareText)}`);
  const copy = () => navigator.clipboard.writeText(me.refLink).then(() => { haptic("medium"); toast(L.copied, "ok"); }, () => toast(me.refLink));
  const finished = me.tasks.filter((t) => t.done).length;
  return [
    h("section", { class: "hero mint" }, h("i", { class: "glow" }),
      h("div", { class: "hero-top" }, h("span", { class: "tile glass" }, ico("users", 24)), h("div", { class: "hero-name" }, h("h1", {}, L.bonusTitle))),
      h("p", { class: "deal" }, plain(me.deal)),
      h("button", { class: "reflink", onclick: copy }, h("span", {}, me.refLink.replace("https://", "")), ico("copy", 17)),
      h("div", { class: "stats two" }, stat(me.friends, L.invited), stat(me.friendsCounted, L.counted)),
      h("button", { class: "btn white", onclick: share }, ico("share", 18), L.share)),
    me.pending ? h("button", { class: "btn success", onclick: collect }, ico("gift", 18), fill(L.collect, { n: me.pending })) : null,
    sectionHead(L.tasks, h("span", { class: "counter" }, `${finished}/${me.tasks.length}`)),
    h("div", { class: "track" }, h("i", { style: { width: `${me.tasks.length ? (finished / me.tasks.length) * 100 : 0}%` } })),
    h("div", { class: "list" }, me.tasks.map(taskRow)),
    sectionHead(L.promo),
    promoBox(),
  ];
}

// ---------- профиль ----------

async function saveSetting(patch) {
  try {
    await api("settings", patch);
    await load();
  } catch (e) { toast(L.failed, "bad"); render(); }
}
function textPage(kind, title) {
  return () => {
    const box = h("section", { class: "card" }, h("div", { class: "skeleton" }), h("div", { class: "skeleton short" }));
    api(`page/${kind}`).then(({ text }) => box.replaceChildren(rich(text))).catch(() => box.replaceChildren(h("p", { class: "muted" }, L.failed)));
    return [h("h1", { class: "page-title" }, title), box];
  };
}
function planCards() {
  const month = (me.plans.find((p) => p.id === "p30") || {}).stars;
  const label = { 7: L.plan7, 30: L.plan30, 90: L.plan90 };
  return me.plans.map((p) => {
    const saving = p.days === 90 && month ? Math.round((1 - p.stars / (3 * month)) * 100) : 0;
    return h("button", { class: "plan" + (p.recurring ? " best" : ""), onclick: () => buy(p.id) },
      p.recurring ? h("span", { class: "plan-tag" }, L.hit) : null,
      h("span", { class: "main" }, h("b", {}, label[p.days]),
        h("small", {}, fill(L.perDay, { n: Math.max(1, Math.round(p.stars / p.days)) }) + (p.recurring ? ` · ${L.renew}` : ""))),
      saving > 0 ? h("span", { class: "pill ok" }, fill(L.saving, { n: saving })) : null,
      h("span", { class: "stars" }, ico("star", 17), String(p.stars)));
  });
}
async function buy(plan) {
  try {
    const { link } = await api("invoice", { plan });
    tg.openInvoice(link, (status) => { if (status === "paid") { success(); setTimeout(() => load("fade"), 1500); } });
  } catch (e) { toast(e.code === 400 ? L.siteDown : L.failed, "bad"); }
}
function cancelRenew() {
  confirmSheet(L.cancelConfirm, L.cancelConfirmText, L.turnOff, true, async () => {
    try { await api("premium/cancel", {}); await load(); toast(L.cancelled, "ok"); }
    catch (e) { toast(L.failed, "bad"); }
  });
}
function useGuarantee() {
  confirmSheet(L.guaranteeTitle, L.guaranteeText, L.guaranteeYes, true, async () => {
    try { const { text } = await api("guarantee", {}); toast(text, "ok"); await load(); }
    catch (e) { toast(e.data && e.data.text ? e.data.text : L.failed, "bad"); }
  });
}
function profileScreen() {
  const left = me.premiumUntil * 1000 > Date.now() ? Math.max(1, Math.ceil((me.premiumUntil * 1000 - Date.now()) / 86400000)) : 0;
  return [
    h("section", { class: "hero gem" }, h("i", { class: "glow" }),
      h("div", { class: "hero-top" },
        h("div", { class: "avatar" }, (me.name || "O").charAt(0).toUpperCase()),
        h("div", { class: "hero-name" }, h("h1", {}, me.name || "OkSita"), h("small", {}, ico("gem", 14), L.planActive)),
        langChip()),
      h("div", { class: "stats two" }, stat(left ? fill(L.planLeft, { n: left }) : L.planNoEnd, left ? planLine() : "Premium"), stat(`${me.used}/${me.limit}`, L.statOffices))),
    me.autoRenew ? h("div", { class: "row static" }, h("span", { class: "tile sm ok" }, ico("refresh", 20)),
      h("span", { class: "main" }, h("b", {}, L.autoRenew), h("small", {}, L.autoOn)), h("button", { class: "mini", onclick: cancelRenew }, L.turnOff)) : null,
    me.inTrial ? h("div", { class: "trial-note" }, ico("gift", 18), h("span", {}, fill(L.trialBanner, { left: trialLeft() }))) : null,
    left && !me.autoRenew ? [sectionHead(L.extend), h("div", { class: "list" }, me.outage ? notice(L.outage) : planCards())] : null,
    me.guarantee === "ready" ? row("shield", L.guaranteeBtn, null, useGuarantee) : null,
    me.guarantee === "wait" ? h("p", { class: "muted small center" }, L.guaranteeWait) : null,
    sectionHead(L.language),
    langGrid(),
    sectionHead(L.settings),
    h("div", { class: "group" },
      toggle("moon", L.quiet, L.quietHint, me.quiet, (on) => saveSetting({ quiet: on })),
      toggle("megaphone", L.partner, L.partnerHint, me.adsOk, (on) => saveSetting({ ads: on }))),
    sectionHead(L.info),
    h("div", { class: "group" },
      row("case", L.boardTitle, null, () => push(boardScreen)),
      row("help", L.howItWorks, null, () => push(textPage("help", L.howItWorks))),
      row("shield", L.forUkr, null, () => push(textPage("ukraine", L.forUkr))),
      row("doc", L.terms, null, () => push(textPage("terms", L.terms))),
      row("lock", L.privacy, null, () => push(textPage("privacy", L.privacy))),
      row("chat", L.openBot, null, openBot),
      tg && tg.addToHomeScreen && tg.isVersionAtLeast("8.0") ? row("phone", L.addHome, null, () => tg.addToHomeScreen()) : null),
    h("p", { class: "muted small center" }, L.disclaimer),
  ];
}

// ---------- пробный период ----------

function trialSheet() {
  sheet(fill(L.trialTitle, { d: me.trialDays }), (body, close) => {
    const point = (icon, text) => h("div", { class: "point" }, h("span", { class: "tile sm ok" }, ico(icon, 19)), h("span", {}, text));
    body.append(h("div", { class: "points" },
      point("home", L.trialP1),
      point("bolt", fill(L.trialP2, { fast: me.top.interval, slow: me.free.interval })),
      point("pin", fill(L.trialP3, { top: me.top.subs, free: me.free.subs })),
      point("radar", L.trialP4)),
      h("p", { class: "muted small" }, L.trialFine),
      h("button", { class: "btn success", onclick: () => startTrial(close) }, ico("gift", 18), L.trialStart));
  });
}
async function startTrial(close) {
  try {
    await api("trial", {});
    close();
    success();
    await load("fade");
    welcomeSheet();
  } catch (e) {
    close();
    toast(e.data && e.data.text ? e.data.text : L.failed, "bad");
    await load();
  }
}
function welcomeSheet() {
  sheet(L.welcomeTitle, (body, close) => {
    const step = (n, text) => h("div", { class: "point" }, h("span", { class: "tile sm vio" }, h("b", {}, String(n))), h("span", {}, text));
    body.append(h("div", { class: "points" }, step(1, fill(L.welcome1, { n: me.top.interval })), step(2, L.welcome2), step(3, L.welcome3)),
      h("button", { class: "btn", onclick: () => { close(); if (!me.subs.length) addOffice(); } }, L.welcomeGo));
  });
}

// ---------- статистика ----------

function hoursChart(hours) {
  const top = Math.max(...hours, 1);
  return h("div", { class: "chart" }, h("div", { class: "bars" }, hours.map((n, i) =>
    h("i", { class: n ? "on" : "", style: { height: `${Math.max(6, (n / top) * 100)}%` }, title: `${i}:00 · ${n}` }))),
    h("div", { class: "ticks" }, [0, 6, 12, 18, 23].map((t) => h("span", {}, `${t}`))));
}
function statsScreen() {
  const box = h("div", { class: "list" }, h("div", { class: "skeleton" }), h("div", { class: "skeleton short" }));
  api("stats").then(({ items }) => {
    if (!items.length) return box.replaceChildren(emptyBox(ico("bars", 28), null, L.statsEmpty));
    const top = items[0].opens;
    box.replaceChildren(...items.map((g, i) => h("div", { class: "metric" },
      h("div", { class: "metric-top" }, h("span", { class: "place" + (i < 3 ? ` p${i}` : "") }, String(i + 1)),
        h("span", { class: "main" }, h("b", {}, g.city), h("small", {}, g.type)), h("strong", {}, String(g.opens))),
      h("div", { class: "track" }, h("i", { style: { width: `${(g.opens / top) * 100}%` } })),
      h("small", {}, [`${L.statBest} ~${g.best}:00`, g.held ? `${L.statHeld} ${g.held}` : null].filter(Boolean).join(" · ")))));
  }).catch(() => box.replaceChildren(h("p", { class: "muted" }, L.failed)));
  return [h("h1", { class: "page-title" }, L.statsTitle), h("p", { class: "muted center" }, L.statsSub), box, h("p", { class: "muted small center" }, L.statsNote)];
}

// ---------- вакансии и партнёры ----------

function boardScreen() {
  const box = h("div", { class: "list" }, h("div", { class: "skeleton" }));
  const prices = h("p", { class: "muted small center" });
  api("board").then((d) => {
    prices.textContent = (d.freeJob ? `${L.boardFree}. ` : "") + fill(L.boardPrices, { job: d.job, ad: d.ad });
    box.replaceChildren(...(d.posts.length ? d.posts.map((p) => h("button", { class: "post", onclick: () => openAny(p.link) },
      h("span", { class: "pill " + (p.kind === "job" ? "ok" : "vio") }, p.kind === "job" ? L.kindJob : L.kindAd),
      h("p", {}, p.text.length > 180 ? `${p.text.slice(0, 180)}…` : p.text))) : [emptyBox(ico("case", 28), null, L.boardEmpty)]));
  }).catch(() => box.replaceChildren(h("p", { class: "muted" }, L.failed)));
  const start = (section) => () => { openTg(`https://t.me/${me.bot}?start=${section}`); if (tg) tg.close(); };
  return [
    h("section", { class: "hero dusk" }, h("i", { class: "glow" }), h("div", { class: "hero-copy wide" }, h("h1", {}, L.boardTitle), h("p", {}, L.boardText)),
      h("button", { class: "btn white", onclick: start("post") }, ico("case", 18), L.boardPost)),
    prices,
    box,
    h("div", { class: "group" },
      row("handshake", L.boardPartner, null, start("partner")),
      row("megaphone", L.boardChannel, null, () => openAny(me.channel))),
  ];
}

// ---------- без Premium ----------

function lockedScreen() {
  const feature = (icon, name, free, top) => h("div", { class: "feature" }, h("span", { class: "tile sm" }, ico(icon, 18)), h("b", {}, name), h("span", {}, free), h("strong", {}, top));
  return [
    h("section", { class: "hero gem lockhero" }, h("i", { class: "glow" }), h("div", { class: "lock-lang" }, langChip()),
      h("div", { class: "gem-mark" }, ico("gem", 44)), h("h1", {}, L.lockedTitle), h("p", {}, L.lockedText),
      me.trial ? h("button", { class: "btn white trial-cta", onclick: trialSheet }, ico("gift", 19), fill(L.trialBtn, { d: me.trialDays })) : null,
      me.trial ? h("small", { class: "trial-once" }, L.trialOnce) : null),
    h("section", { class: "card" },
      h("div", { class: "feature head" }, h("i"), h("i"), h("span", {}, L.free), h("strong", {}, "Premium")),
      feature("pin", L.rowOffices, String(me.free.subs), String(me.top.subs)),
      feature("bolt", L.rowCheck, `${me.free.interval} ${L.min}`, `${me.top.interval} ${L.min}`),
      feature("radar", L.rowRadar, L.radarFree, L.unlimited),
      feature("globe", L.rowRange, fill(L.km, { n: 100 }), fill(L.km, { n: 250 })),
      feature("id", L.rowSignals, String(me.free.signals), String(me.top.signals)),
      feature("home", L.rowApp, L.no, L.yes),
      feature("megaphone", L.rowAds, L.adsConsent, L.adsNone)),
    me.outage ? notice(L.outage) : h("div", { class: "list" }, planCards()),
    me.outage ? null : h("p", { class: "muted small center" }, L.payNote),
    sectionHead(L.haveCode),
    promoBox(),
    h("button", { class: "btn quiet", onclick: openBot }, ico("gift", 18), L.freeWay),
  ];
}

const SCREENS = { home: homeScreen, radar: radarScreen, docs: docsScreen, bonus: bonusScreen, profile: profileScreen };

// ---------- запуск ----------

function applyTheme() {
  document.documentElement.dataset.theme = (tg && tg.colorScheme) || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}
function failScreen(title, retry) {
  root.replaceChildren(h("div", { class: "splash failed" }, h("img", { src: "/app/mark.svg", alt: "" }), h("p", {}, title),
    retry ? h("button", { class: "btn", onclick: retry }, L.retry) : null));
}
(async function start() {
  applyTheme();
  if (tg) {
    tg.ready();
    tg.expand();
    const newer = (v) => tg.isVersionAtLeast && tg.isVersionAtLeast(v);
    if (newer("6.1")) { tg.BackButton.onClick(onBack); tg.setHeaderColor("secondary_bg_color"); tg.setBackgroundColor("secondary_bg_color"); }
    if (newer("7.7")) tg.disableVerticalSwipes();
    tg.onEvent("themeChanged", applyTheme);
  }
  const guess = (navigator.language || "en").slice(0, 2);
  if (T[guess]) L = T[guess];
  if (!initData) return failScreen(L.needTelegram);
  const boot = async () => {
    try { await load("fade"); setInterval(refresh, 45000); }
    catch (e) { if (e.code === 403) failScreen("🚫"); else failScreen(L.errorTitle, boot); }
  };
  await boot();
})();
