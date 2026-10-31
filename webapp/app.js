"use strict";
const tg = window.Telegram && window.Telegram.WebApp;
const initData = (tg && tg.initData) || "";
const root = document.getElementById("app");
const T = {
  ru: {
    offices: "Офисы", bonus: "Бонусы", premium: "Premium", until: "до", officesShort: "офисы", next: "проверка", alerts: "уведомлений",
    add: "Добавить офис", empty: "Пока нет офисов. Добавь первый — и бот начнёт следить за датами.",
    searchOffice: "Город или офис", chooseType: "Тип записи", loading: "Загрузка…", min: "мин", now: "сейчас",
    nearest: "Ближайшая дата", hours: "Свободное время", address: "Адрес", filter: "Какие даты присылать", any: "Любые", upTo: "до",
    days: "дн.", pause: "Пауза", resume: "Возобновить", check: "Проверить", remove: "Удалить", book: "Записаться на сайте DGT",
    confirmDelete: "Удалить этот офис из подписок?", history: "Когда появлялись места", noHistory: "Пока мест здесь не появлялось.",
    held: "держались", still: "ещё есть", min2: "мин", many: "много", mid: "средне", few: "мало", noDates: "Свободных дат сейчас нет. Бот напишет, как только появятся.",
    outage: "Сайт DGT сейчас недоступен для проверок. Данные могут быть неактуальны.",
    invite: "Пригласи друга", inviteText: "Ты и друг получите бонус Premium, когда он добавит офис.", copy: "Копировать", copied: "Скопировано", share: "Поделиться",
    invited: "Приглашено", counted: "Засчитано", tasks: "Задания и промокоды", openBot: "Открыть в боте",
    lockedTitle: "Мини-приложение — для Premium", lockedText: "Управляй офисами в удобном приложении и лови даты раньше.",
    free: "Бесплатно", officesRow: "Офисов", intervalRow: "Проверка", radarRow: "Радар", appRow: "Приложение", adsRow: "Реклама", radarFree: "1 в день", radarTop: "без лимита", yes: "да", no: "нет", noAds: "нет", ads: "по согласию",
    plan7: "7 дней", plan30: "30 дней", plan90: "90 дней", renew: "автопродление", free2: "Получить бесплатно за задания", perDay: "⭐ в день", hit: "Хит",
    limit: "Лимит офисов исчерпан", failed: "Не получилось, попробуй ещё раз", demo: "DEMO", checking: "Проверка запущена", wait: "Подожди минуту", siteDown: "Сайт DGT недоступен",
    needTelegram: "Открой приложение из Telegram.", booked: "Запись",
    mo: ["Январь","Февраль","Март","Апрель","Май","Июнь","Июль","Август","Сентябрь","Октябрь","Ноябрь","Декабрь"], wd: ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"],
  },
  uk: {
    offices: "Офіси", bonus: "Бонуси", premium: "Premium", until: "до", officesShort: "офіси", next: "перевірка", alerts: "сповіщень",
    add: "Додати офіс", empty: "Поки немає офісів. Додай перший — і бот почне стежити за датами.",
    searchOffice: "Місто або офіс", chooseType: "Тип запису", loading: "Завантаження…", min: "хв", now: "зараз",
    nearest: "Найближча дата", hours: "Вільний час", address: "Адреса", filter: "Які дати надсилати", any: "Будь-які", upTo: "до",
    days: "дн.", pause: "Пауза", resume: "Відновити", check: "Перевірити", remove: "Видалити", book: "Записатися на сайті DGT",
    confirmDelete: "Видалити цей офіс із підписок?", history: "Коли з’являлися місця", noHistory: "Поки місць тут не з’являлося.",
    held: "трималися", still: "ще є", min2: "хв", many: "багато", mid: "середньо", few: "мало", noDates: "Вільних дат зараз немає. Бот напише, щойно з’являться.",
    outage: "Сайт DGT зараз недоступний для перевірок. Дані можуть бути неактуальні.",
    invite: "Запроси друга", inviteText: "Ти й друг отримаєте бонус Premium, коли він додасть офіс.", copy: "Копіювати", copied: "Скопійовано", share: "Поділитися",
    invited: "Запрошено", counted: "Зараховано", tasks: "Завдання та промокоди", openBot: "Відкрити в боті",
    lockedTitle: "Міні-застосунок — для Premium", lockedText: "Керуй офісами у зручному застосунку й лови дати раніше.",
    free: "Безкоштовно", officesRow: "Офісів", intervalRow: "Перевірка", radarRow: "Радар", appRow: "Застосунок", adsRow: "Реклама", radarFree: "1 на день", radarTop: "без ліміту", yes: "так", no: "ні", noAds: "немає", ads: "за згодою",
    plan7: "7 днів", plan30: "30 днів", plan90: "90 днів", renew: "автопродовження", free2: "Отримати безкоштовно за завдання", perDay: "⭐ на день", hit: "Хіт",
    limit: "Ліміт офісів вичерпано", failed: "Не вдалося, спробуй ще раз", demo: "DEMO", checking: "Перевірку запущено", wait: "Зачекай хвилину", siteDown: "Сайт DGT недоступний",
    needTelegram: "Відкрий застосунок із Telegram.", booked: "Запис",
    mo: ["Січень","Лютий","Березень","Квітень","Травень","Червень","Липень","Серпень","Вересень","Жовтень","Листопад","Грудень"], wd: ["Пн","Вт","Ср","Чт","Пт","Сб","Нд"],
  },
};
let me = null, L = T.ru, tab = "offices", stack = [];

function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined && v !== false) el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) el.append(kid);
  return el;
}
const tone = (status) => ({ "🟢": "ok", "🟡": "warn", "🔴": "bad" }[status] || "");
const haptic = (kind) => { try { tg.HapticFeedback.impactOccurred(kind || "light"); } catch (e) { /* не в Telegram */ } };
const toast = (text) => { if (tg && tg.showAlert && tg.isVersionAtLeast && tg.isVersionAtLeast("6.2")) tg.showAlert(text); else alert(text); };
function page(...kids) {
  const nav = kids.find((k) => k && k.tagName === "NAV");  // нижнее меню — вне анимированного блока, иначе fixed не работает
  root.replaceChildren(...[h("div", { class: "view" }, ...kids.filter((k) => k !== nav)), nav].filter(Boolean));
  window.scrollTo(0, 0);
}

async function api(path, body) {
  const res = await fetch("/api/" + path, {
    method: body ? "POST" : "GET",
    headers: { "X-Init-Data": initData, "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { const err = new Error(data.error || data.status || res.status); err.code = res.status; err.data = data; throw err; }
  return data;
}

function back(fn) {
  if (!tg || !tg.BackButton) return;
  tg.BackButton.offClick(onBack);
  stack = fn ? [fn] : [];
  if (fn) { tg.BackButton.show(); tg.BackButton.onClick(onBack); } else tg.BackButton.hide();
}
function onBack() { const fn = stack.pop(); if (fn) fn(); }

function mainButton(text, fn) {
  if (!tg || !tg.MainButton) return;
  tg.MainButton.offClick(mainButton.fn || (() => {}));
  mainButton.fn = fn;
  if (text) { tg.MainButton.setText(text); tg.MainButton.onClick(fn); tg.MainButton.show(); } else tg.MainButton.hide();
}

function fmtDate(iso) {
  const d = new Date(iso + "T12:00:00");
  return d.getDate() + " " + L.mo[d.getMonth()].toLowerCase().slice(0, 3);
}
function fmtTs(ts) {
  const d = new Date(ts * 1000);
  return String(d.getDate()).padStart(2, "0") + "." + String(d.getMonth() + 1).padStart(2, "0") + " " +
    String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
}

async function load() {
  me = await api("me");
  L = T[me.lang] || T.ru;
  document.documentElement.lang = me.lang;
  render();
}

function render() {
  if (!me.premium) return locked();
  if (tab === "offices") officesTab(); else bonusTab();
}

function tabs() {
  const item = (id, ico, label) => h("button", { class: tab === id ? "on" : "", onclick: () => { haptic(); tab = id; render(); } }, h("b", {}, ico), label);
  return h("nav", { class: "tabs" }, item("offices", "🏢", L.offices), item("bonus", "🎁", L.bonus));
}

function hero() {
  const mins = me.nextCheck ? Math.max(0, Math.ceil((me.nextCheck * 1000 - Date.now()) / 60000)) : null;
  const until = me.premiumUntil * 1000 > Date.now() ? ` ${L.until} ${fmtTs(me.premiumUntil).slice(0, 5)}` : "";
  return h("section", { class: "hero" },
    h("span", { class: "tag" }, L.demo),
    h("div", { class: "hero-top" }, h("img", { class: "logo", src: "/app/mark.svg", alt: "" }),
      h("div", {}, h("h1", {}, "OkSita"), h("small", {}, h("i", { class: "live" }), `${L.premium}${until}`))),
    h("div", { class: "stats" },
      h("div", { class: "stat" }, h("b", {}, `${me.used}/${me.limit}`), h("span", {}, L.officesShort)),
      h("div", { class: "stat" }, h("b", {}, mins === null ? "—" : mins === 0 ? L.now : `${mins} ${L.min}`), h("span", {}, L.next)),
      h("div", { class: "stat" }, h("b", {}, String(me.alerts)), h("span", {}, L.alerts))));
}

function officesTab() {
  back(null);
  mainButton(me.used < me.limit ? "➕ " + L.add : null, addOffice);
  const rows = me.subs.map((s) => h("button", { class: "row", onclick: () => { haptic(); detail(s.id); } },
    h("div", { class: "ico " + tone(s.status) }, s.emoji),
    h("div", { class: "main" }, h("div", { class: "title" }, s.city), h("div", { class: "sub" }, s.type)),
    h("span", { class: "pill " + tone(s.status) }, s.nearest ? fmtDate(s.nearest) : s.status), h("span", { class: "chev" }, "›")));
  page(hero(), me.outage ? h("div", { class: "notice" }, "🛑 " + L.outage) : null,
    rows.length ? h("div", { class: "list" }, rows)
      : h("div", { class: "empty" }, h("img", { src: "/app/mark.svg", alt: "" }), L.empty), tabs());
}

async function detail(id, month) {
  const sub = me.subs.find((s) => s.id === id);
  if (!sub) return officesTab();
  back(officesTab);
  mainButton(null);
  const days = new Map(sub.days);
  const months = [...new Set(sub.days.map((d) => d[0].slice(0, 7)))].sort();
  let idx = month === undefined ? 0 : month;
  const calBox = h("div", {});
  const drawCal = () => {
    if (!months.length) return calBox.replaceChildren(h("div", { class: "empty" }, L.noDates));
    idx = (idx + months.length) % months.length;
    const [y, m] = months[idx].split("-").map(Number);
    const first = (new Date(y, m - 1, 1).getDay() + 6) % 7;
    const total = new Date(y, m, 0).getDate();
    const cells = L.wd.map((w) => h("span", {}, w));
    for (let i = 0; i < first; i++) cells.push(h("div", {}));
    for (let d = 1; d <= total; d++) {
      const iso = `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      const load = days.get(iso);
      cells.push(h("div", { class: "day " + ({ "🟢": "g", "🟡": "y", "🔴": "r" }[load] || "") }, String(d)));
    }
    calBox.replaceChildren(
      h("div", { class: "cal-head" },
        months.length > 1 ? h("button", { onclick: () => { idx--; drawCal(); } }, "‹") : h("i"),
        `${L.mo[m - 1]} ${y}`,
        months.length > 1 ? h("button", { onclick: () => { idx++; drawCal(); } }, "›") : h("i")),
      h("div", { class: "cal" }, cells),
      h("div", { class: "legend" }, ["g", "y", "r"].map((c, i) => h("span", {},
        h("i", { class: ["dot-g", "dot-y", "dot-r"][i] }), [L.many, L.mid, L.few][i]))));
  };
  drawCal();
  const historyBox = h("div", { class: "card" }, h("h2", {}, L.history), h("div", { class: "sub" }, L.loading));
  const chips = [0, 7, 14, 30, 60].map((v) => h("button", {
    class: "chip" + (sub.filter === v ? " on" : ""),
    onclick: () => act(() => api(`subs/${id}/filter`, { days: v }), id),
  }, v ? `${L.upTo} ${v} ${L.days}` : L.any));
  page(
    h("section", { class: "card office" },
      h("div", { class: "office-top" }, h("div", { class: "ico big " + tone(sub.status) }, sub.emoji),
        h("div", {}, h("h1", {}, sub.city), h("div", { class: "sub" }, sub.type))),
      h("div", {}, h("span", { class: "pill " + tone(sub.status) }, `${sub.status} ${sub.statusText}`)),
      sub.address || sub.schedule ? h("div", { class: "facts" },
        sub.address ? h("div", { class: "sub" }, `📍 ${sub.address}`) : null,
        sub.schedule ? h("div", { class: "sub" }, `🕘 ${sub.schedule}`) : null) : null),
    sub.nearest ? h("section", { class: "card nearest" }, h("h2", {}, L.nearest), h("b", {}, fmtDate(sub.nearest)),
      sub.hours.length ? h("div", { class: "hours" }, sub.hours.slice(0, 16).map((t) => h("span", {}, t))) : null) : null,
    h("section", { class: "card" }, calBox),
    h("section", { class: "card" }, h("h2", {}, L.filter), h("div", { class: "segment" }, chips)),
    h("div", { class: "actions" },
      h("button", { class: "btn wide", onclick: () => openLink("https://sedeclave.dgt.gob.es/WEB_CITE_CONSULTA/paginas/inicio.faces") }, "📝 " + L.book),
      sub.booked ? null : h("button", { class: "btn ghost", onclick: () => act(() => api(`subs/${id}/pause`, { paused: !sub.paused }), id) }, sub.paused ? "▶️ " + L.resume : "⏸ " + L.pause),
      h("button", { class: "btn ghost", onclick: () => checkNow(id) }, "🔄 " + L.check),
      h("button", { class: "btn danger wide", onclick: () => removeSub(id) }, "🗑 " + L.remove)),
    historyBox);
  try {
    const { events } = await api(`subs/${id}/history`);
    historyBox.replaceChildren(h("h2", {}, L.history), events.length ? h("div", { class: "list" }, events.map((e) =>
      h("div", { class: "sub" }, `${fmtTs(e.at)} — ${e.closed ? `${L.held} ${Math.max(1, Math.round((e.closed - e.at) / 60))} ${L.min2}` : L.still}`)))
      : h("div", { class: "sub" }, L.noHistory));
  } catch (e) { historyBox.remove(); }
}

function openLink(url) { if (tg && tg.openLink) tg.openLink(url); else window.open(url, "_blank", "noopener"); }

async function act(fn, id) {
  try {
    await fn();
    haptic("medium");
    await load();
    if (id !== undefined && me.subs.some((s) => s.id === id)) detail(id);
  } catch (e) {
    toast(e.code === 409 ? L.limit : L.failed);
  }
}

async function checkNow(id) {
  try { await api(`subs/${id}/check`, {}); toast(L.checking); }
  catch (e) { toast(e.code === 429 ? L.wait : e.code === 503 ? L.siteDown : L.failed); }
}

function removeSub(id) {
  const run = (ok) => { if (ok) act(() => api(`subs/${id}/delete`, {})); };
  if (tg && tg.showConfirm && tg.isVersionAtLeast && tg.isVersionAtLeast("6.2")) tg.showConfirm(L.confirmDelete, run); else run(confirm(L.confirmDelete));
}

async function addOffice() {
  back(officesTab);
  mainButton(null);
  root.replaceChildren(h("div", { class: "center" }, h("div", { class: "spinner" })));
  let offices = [];
  try { offices = (await api("offices")).offices; } catch (e) { toast(L.failed); return officesTab(); }
  const list = h("div", { class: "list" });
  const fold = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const draw = (q) => list.replaceChildren(...offices.filter((o) => fold(o.city).includes(fold(q))).slice(0, 40).map((o) =>
    h("button", { class: "row", onclick: () => pickType(o) }, h("div", { class: "main" }, h("div", { class: "title" }, o.city)), h("span", { class: "chev" }, "›"))));
  const input = h("input", { class: "search", placeholder: L.searchOffice, autocomplete: "off", oninput: (e) => draw(e.target.value) });
  draw("");
  page(input, list);
}

async function pickType(office) {
  back(addOffice);
  root.replaceChildren(h("div", { class: "center" }, h("div", { class: "spinner" }), L.loading));
  try {
    const { areas } = await api(`areas?office=${encodeURIComponent(office.id)}`);
    page(h("div", { class: "card" }, h("h2", {}, L.chooseType), h("b", {}, office.city)), h("div", { class: "list" }, areas.map((a) =>
      h("button", { class: "row", onclick: () => addSub(office.id, a.code) }, h("div", { class: "ico" }, a.emoji),
        h("div", { class: "main" }, h("div", { class: "title" }, a.label), a.hint ? h("div", { class: "sub" }, a.hint) : null)))));
  } catch (e) { toast(e.code === 503 ? L.siteDown : L.failed); addOffice(); }
}

async function addSub(centro, area) {
  try { await api("subs", { centro, area }); haptic("medium"); tab = "offices"; await load(); }
  catch (e) { toast(e.code === 409 ? L.limit : L.failed); }
}

function bonusTab() {
  back(null);
  mainButton(null);
  const copy = () => { navigator.clipboard.writeText(me.refLink).then(() => toast(L.copied), () => toast(me.refLink)); };
  const share = () => { const url = "https://t.me/share/url?url=" + encodeURIComponent(me.refLink); if (tg && tg.openTelegramLink) tg.openTelegramLink(url); else openLink(url); };
  page(
    h("section", { class: "mint" },
      h("div", { class: "mint-top" }, h("span", { class: "big" }, "🎁"), h("div", {}, h("h1", {}, L.invite), h("div", { class: "mint-text" }, L.inviteText))),
      h("div", { class: "link" }, me.refLink),
      h("div", { class: "actions" }, h("button", { class: "btn white", onclick: share }, "📤 " + L.share), h("button", { class: "btn glass", onclick: copy }, "🔗 " + L.copy))),
    h("section", { class: "card" }, h("div", { class: "stats two" },
      h("div", { class: "count" }, h("b", {}, String(me.friends)), h("div", { class: "sub" }, L.invited)),
      h("div", { class: "count" }, h("b", {}, String(me.friendsCounted)), h("div", { class: "sub" }, L.counted)))),
    h("button", { class: "row", onclick: openBot }, h("div", { class: "ico ok" }, "📝"), h("div", { class: "main" }, h("div", { class: "title" }, L.tasks), h("div", { class: "sub" }, L.openBot)), h("span", { class: "chev" }, "›")),
    tabs());
}
function openBot() { const url = `https://t.me/${me.bot}`; if (tg && tg.openTelegramLink) { tg.openTelegramLink(url); tg.close(); } else openLink(url); }

function locked() {
  back(null);
  mainButton(null);
  const row = (name, a, b) => h("tr", {}, h("td", {}, name), h("td", {}, a), h("td", {}, b));
  const label = { 7: L.plan7, 30: L.plan30, 90: L.plan90 };
  const plans = me.outage ? [h("div", { class: "notice" }, "🛑 " + L.outage)] : me.plans.map((p) => h("button", { class: "plan" + (p.recurring ? " best" : ""), onclick: () => buy(p.id) },
    p.recurring ? h("span", { class: "badge" }, L.hit) : null,
    h("div", {}, h("div", { class: "plan-name" }, label[p.days]),
      h("div", { class: "sub" }, `≈ ${Math.max(1, Math.round(p.stars / p.days))} ${L.perDay}${p.recurring ? " · " + L.renew : ""}`)),
    h("div", { class: "plan-price" }, `⭐ ${p.stars}`)));
  page(
    h("section", { class: "gem" }, h("span", { class: "tag" }, L.demo), h("div", { class: "gem-ico" }, "💎"), h("h1", {}, L.lockedTitle), h("p", {}, L.lockedText)),
    h("section", { class: "card" }, h("table", { class: "compare" },
      h("tr", {}, h("th", {}), h("th", {}, L.free), h("th", {}, L.premium)),
      row(L.officesRow, String(me.free.subs), String(me.top.subs)),
      row(L.intervalRow, `${me.free.interval} ${L.min}`, `${me.top.interval} ${L.min}`),
      row(L.radarRow, L.radarFree, L.radarTop), row(L.appRow, L.no, L.yes), row(L.adsRow, L.ads, L.noAds))),
    h("div", { class: "list" }, plans),
    h("button", { class: "btn ghost", onclick: openBot }, "🎁 " + L.free2));
}

async function buy(plan) {
  try {
    const { link } = await api("invoice", { plan });
    tg.openInvoice(link, (status) => { if (status === "paid") { haptic("heavy"); setTimeout(load, 1500); } });
  } catch (e) { toast(L.failed); }
}

(async function start() {
  if (tg) { tg.ready(); tg.expand(); try { tg.setHeaderColor("secondary_bg_color"); tg.setBackgroundColor("secondary_bg_color"); } catch (e) { /* старые клиенты */ } }
  if (!initData) { root.replaceChildren(h("div", { class: "center" }, T.ru.needTelegram)); return; }
  try { await load(); }
  catch (e) { root.replaceChildren(h("div", { class: "center" }, e.code === 403 ? "🚫" : L.failed)); }
})();
