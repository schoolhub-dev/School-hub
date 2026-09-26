// ============================================================================
// Deno Deploy воркер «Школьный Хаб»: /moderate + /parse/google + /parse/nikasoft
// ----------------------------------------------------------------------------
//   POST   /moderate       { text, nick, model? }        -> { bad, category, reason }
//   POST   /parse/google   { cid, sid, clid, city, school, className, class }
//                                                       -> { updated: 0..1 }
//   POST   /parse/nikasoft { cid, sid, clid, school, allClasses, className }
//                                                       -> { updated: N }
//   OPTIONS любые          -> 204 + CORS
//
// Без npm-зависимостей: только Web API (fetch, DOMParser, DecompressionStream)
// и встроенные модули Deno (Deno.serve, Deno.env).
//
// Env-переменные (Deno Deploy → Settings → Environment Variables):
//   XKIRO_API_KEY     ключ xKiro для /moderate
//   FIREBASE_API_KEY  apiKey проекта (для identitytoolkit signUp -> idToken)
//   FIREBASE_DB_URL   опционально, по умолчанию school-hub-9d8aa
//   GOOGLE_SHEETS_ID  опционально, по умолчанию id таблицы расписания
//   NIKA_URL          опционально, по умолчанию raspisanie.nikasoft.ru/86111512.html
// ============================================================================

// ----------------------------- CORS и helpers ------------------------------

const cors = () => ({
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
  "Access-Control-Max-Age": "86400",
  "Content-Type": "application/json",
});

const json = (obj, status = 200) =>
  new Response(JSON.stringify(obj), { status, headers: cors() });

const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36";

async function httpBytes(url) {
  const res = await fetch(url, {
    headers: { "User-Agent": UA, "Accept-Language": "ru,en;q=0.9" },
  });
  if (!res.ok) throw new Error(url + " -> HTTP " + res.status);
  return new Uint8Array(await res.arrayBuffer());
}

async function httpText(url) {
  const res = await fetch(url, {
    headers: { "User-Agent": UA, "Accept-Language": "ru,en;q=0.9" },
  });
  if (!res.ok) throw new Error(url + " -> HTTP " + res.status);
  return await res.text();
}

const normKey = (s) => String(s || "").replace(/\s+/g, "").toLowerCase();
const strip = (s) =>
  s == null ? "" : String(s).replace(/\u00a0/g, " ").trim();

// ------------------------------- Firebase ----------------------------------

const DEFAULT_DB = "https://school-hub-9d8aa-default-rtdb.firebaseio.com";
const FIREBASE_API_KEY = () => Deno.env.get("FIREBASE_API_KEY") || "";
const FIREBASE_DB = () =>
  (Deno.env.get("FIREBASE_DB_URL") || DEFAULT_DB).replace(/\/+$/, "") + "/";

// idToken анонимной сессии (как в parse_schedule.py: accounts:signUp).
async function firebaseToken() {
  const key = FIREBASE_API_KEY();
  if (!key) throw new Error("FIREBASE_API_KEY не настроен");
  const res = await fetch(
    "https://identitytoolkit.googleapis.com/v1/accounts:signUp?key=" + key,
    { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ returnSecureToken: true }) },
  );
  if (!res.ok) throw new Error("Firebase auth: HTTP " + res.status);
  const j = await res.json();
  return j.idToken;
}

async function fbGet(path) {
  const res = await fetch(FIREBASE_DB() + path + ".json");
  if (!res.ok) return null;
  return await res.json();
}

async function fbExists(path) {
  return fbGet(path).then((v) => v != null);
}

async function fbPut(path, obj) {
  console.log("Записываю в Firebase… (" + path + ")");
  const token = await firebaseToken();
  const url = FIREBASE_DB() + path + ".json?auth=" + encodeURIComponent(token);
  const res = await fetch(url, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(obj),
  });
  if (!res.ok) throw new Error("Firebase PUT: HTTP " + res.status);
  return res;
}

// Сравнение: канонизируем (сортируем ключи) и сравниваем как JSON-строки.
function canon(x) {
  if (x == null || typeof x !== "object" || Array.isArray(x)) return JSON.stringify(x);
  const out = {};
  for (const k of Object.keys(x).sort()) out[k] = canon(x[k]);
  return JSON.stringify(out);
}
const equal = (a, b) => canon(a) === canon(b);

// ------------------------ Даты (часовой пояс МСК) ---------------------------

// МСК = UTC+3 (Deno Deploy по умолчанию UTC — сдвигаем вручную).
const MSK = 3 * 3600 * 1000;
const todayDate = () => {
  const d = new Date(Date.now() + MSK);
  return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
};
// понедельник недели, содержащей d (d — Date UTC, время 00:00)
const weekStart = (d) => {
  const wd = (d.getUTCDay() + 6) % 7; // 0 = пн
  return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() - wd));
};
const dateOf = (y, mo, day) => new Date(Date.UTC(y, mo - 1, day));
const fmtD = (d) =>
  String(d.getUTCDate()).padStart(2, "0") + "." +
  String(d.getUTCMonth() + 1).padStart(2, "0") + "." + d.getUTCFullYear();
// fmtD к строке «dd.mm.yyyy»
const parseRusDate = (s) => {
  const m = /^(\d{1,2})\.(\d{1,2})\.(\d{2,4})$/.exec(String(s).trim());
  if (!m) return null;
  let yr = parseInt(m[3], 10);
  if (yr < 100) yr += 2000;
  return new Date(Date.UTC(yr, parseInt(m[2], 10) - 1, parseInt(m[1], 10)));
};

// ------------------------------- /moderate ---------------------------------

const XKIRO_URL = "https://api.xkiro.com/v1/chat/completions";
const DEFAULT_MODEL = "qwen/qwen3.6-plus:free";
const SYSTEM_PROMPT =
  "Ты строгий модератор школьного чата. Определи, нарушает ли сообщение правила: " +
  "мат (в т.ч. замаскированный: замена букв символами, латиницей, перестановка, " +
  "\"квас\", \"хрю\", буквы-заглушки), оскорбление, травля, угрозы, грубость, спам/реклама, " +
  "попытка обойти фильтр. Отвечай ТОЛЬКО валидным JSON: " +
  "{\"bad\": true или false, \"category\": \"мат|оскорбление|травля|угрозы|спам|другое|none\", " +
  "\"reason\": \"краткая причина или пустая строка\"}.";

async function handleModerate(body) {
  const key = Deno.env.get("XKIRO_API_KEY");
  if (!key) return json({ error: "XKIRO_API_KEY not configured" }, 500);
  const text = String(body.text || "").slice(0, 600).trim();
  const nick = String(body.nick || "").slice(0, 30);
  const model = String(body.model || DEFAULT_MODEL).slice(0, 80);
  if (!text) return json({ error: "empty_text" }, 400);

  const payload = {
    model,
    temperature: 0,
    max_tokens: 220,
    messages: [
      { role: "system", content: SYSTEM_PROMPT },
      { role: "user", content: "Сообщение для проверки (ник: @" + nick + "):\n" + text },
    ],
  };
  const sendOpt = (extra) =>
    fetch(XKIRO_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": "Bearer " + key },
      body: JSON.stringify(Object.assign({}, payload, extra || {})),
    });

  let upstream;
  try {
    upstream = await sendOpt({ response_format: { type: "json_object" } });
  } catch (e) {
    return json({ error: "upstream_network_error", message: String(e.message || e) }, 502);
  }
  if (upstream.status === 400) {
    try {
      upstream = await sendOpt(null);
    } catch (e) {
      return json({ error: "upstream_network_error", message: String(e.message || e) }, 502);
    }
  }

  let bodyText = "";
  try { bodyText = await upstream.text(); } catch { /* тело недоступно */ }
  console.log("xKiro status:", upstream.status);
  console.log("xKiro body:", bodyText);
  let data = null;
  try { data = JSON.parse(bodyText); } catch { /* не JSON */ }
  const content =
    (data && data.choices && data.choices[0] && data.choices[0].message && data.choices[0].message.content) ||
    "";
  const block = content.match(/\{[\s\S]*\}/);
  if (upstream.ok && block) {
    try {
      const j = JSON.parse(block[0]);
      if (typeof j.bad === "boolean") {
        return json({
          bad: j.bad,
          category: String(j.category || "").slice(0, 30),
          reason: String(j.reason || "").slice(0, 80),
        });
      }
    } catch { /* ниже */ }
  }
  const detail = (data && data.error && (data.error.message || JSON.stringify(data.error))) ||
    content.slice(0, 300);
  return json({ error: "upstream_response", status: upstream.status, detail }, 502);
}

// ============================================================================
// /parse/google — Google Sheets (XLSX-экспорт, запасные пути gviz/htmlview)
// ============================================================================

const GOOGLE_SHEETS_ID = () =>
  Deno.env.get("GOOGLE_SHEETS_ID") || "1qJ6eBCLSWkbQSwqtD2j-70kRf3F8d0IUU-MdP3MQBxQ";

const DAY_MAP = [
  [/понед/i, "mon"], [/вторн/i, "tue"], [/сред/i, "wed"],
  [/четверг/i, "thu"], [/пятниц/i, "fri"], [/суббот/i, "sat"], [/воскрес/i, "sun"],
];
const HUB_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
const DAY_TO_MSK = { mon: 1, tue: 2, wed: 3, thu: 4, fri: 5, sat: 6, sun: 0 }; // getUTCDay
const LESSON_NO = /^\d{1,2}(\.\d+)?$/;
const TIME_TXT = /^\d{1,2}[:.]\d{2}\s*[-–—]\s*\d{1,2}[:.]\d{2}/;
const DATE_IN_NAME = new RegExp(
  "(?:понед|вторн|сред|четверг|пятниц|суббот|воскрес)\\w*\\s*" +
  "(\\d{1,2})\\s*[.,]\\s*(\\d{1,2})\\s*(?:[.,]\\s*(\\d{2,4}))?", "i");

const dayKeyOf = (s) => { for (const [re, k] of DAY_MAP) if (re.test(s)) return k; return null; };
const emptyDays = () => ({ mon: [], tue: [], wed: [], thu: [], fri: [], sat: [], sun: [] });

// «8.15 - 08.55» / «09.05 - 09.45» -> «08:15-08:55»
function fmtTime(cell) {
  if (cell == null) return "";
  const t = strip(cell);
  const parts = t.split(/[-–—]/).map((p) => p.trim()).filter(Boolean);
  const out = [];
  for (const p of parts) {
    const m = /^(\d{1,2})[.,](\d{1,2})$/.exec(p);
    if (!m || m[2].length < 2) return "";
    const h = parseInt(m[1], 10), mi = parseInt(m[2], 10);
    if (!(0 <= h && h <= 23 && 0 <= mi && mi <= 59)) return "";
    out.push(String(h).padStart(2, "0") + ":" + String(mi).padStart(2, "0"));
  }
  return out.join("-");
}
const isWindowCell = (c) => c != null && normKey(String(c)) === "окно";

// ---- Разбор вкладки с датой в названии: «вторник 22.09.2026» -> {key, date} ----
function parseTabDate(name) {
  const m = DATE_IN_NAME.exec(strip(name));
  if (!m) return null;
  const d = parseInt(m[1], 10), mo = parseInt(m[2], 10);
  if (!(1 <= d && d <= 31 && 1 <= mo && mo <= 12)) return null;
  const key = dayKeyOf(String(name));
  if (!key) return null;
  const year = todayDate().getUTCFullYear();
  let years;
  if (m[3]) {
    const yr = parseInt(m[3], 10);
    years = [yr < 100 ? 2000 + yr : yr];
  } else {
    years = [year - 2, year - 1, year, year + 1, year + 2];
  }
  let best = null;
  for (const y of years) {
    const dt = dateOf(y, mo, d);
    if (dt.getUTCDay() !== DAY_TO_MSK[key]) continue;
    if (!best || Math.abs(y - year) < Math.abs(best.getUTCFullYear() - year)) best = dt;
  }
  return best ? { key, date: best } : null;
}

// Отбор вкладок на текущую неделю (строгий проход, как в Python select_week_tabs).
function selectWeekTabs(sheets) {
  const day0 = todayDate();
  const monday = weekStart(day0);
  const sunday = new Date(Date.UTC(monday.getUTCFullYear(), monday.getUTCMonth(), monday.getUTCDate() + 6));
  const year = day0.getUTCFullYear();
  const good = [], loose = [];
  for (const sh of sheets) {
    const name = String(sh.name || "");
    const r = parseTabDate(name);
    if (r && r.date >= monday && r.date <= sunday) { good.push({ key: r.key, date: r.date, name }); continue; }
    const m = DATE_IN_NAME.exec(strip(name));
    if (!m) continue;
    const d = parseInt(m[1], 10), mo = parseInt(m[2], 10);
    if (!(1 <= d && d <= 31 && 1 <= mo && mo <= 12)) continue;
    const key = dayKeyOf(String(name));
    if (!key) continue;
    const yr = m[3] ? (parseInt(m[3], 10) < 100 ? 2000 + parseInt(m[3], 10) : parseInt(m[3], 10)) : year;
    const dt = dateOf(yr, mo, d);
    if (dt >= monday && dt <= sunday) loose.push({ key, date: dt, name });
  }
  if (!good.length) {
    const bySlot = new Map();
    for (const it of loose) if (!bySlot.has(it.key)) bySlot.set(it.key, it);
    return [...bySlot.values()].sort((a, b) => a.date - b.date).map((it) => ({ ...it, strict: false }));
  }
  const byDate = new Map();
  for (const it of good) if (!byDate.has(+it.date)) byDate.set(+it.date, it);
  return [...byDate.values()].sort((a, b) => a.date - b.date).map((it) => ({ ...it, strict: true }));
}

// Колонка нужного класса из матрицы ОДНОЙ датированной вкладки.
function extractClassDay(rows, className) {
  const target = normKey(className);
  let hcol = -1;
  for (let r = 0; r < Math.min(rows.length, 10) && hcol < 0; r++) {
    for (let ci = 0; ci < rows[r].length; ci++) {
      if (rows[r][ci] != null && rows[r][ci] !== "" && normKey(String(rows[r][ci])) === target) { hcol = ci; break; }
    }
  }
  if (hcol < 0) return { lessons: [], found: false };
  const lessons = [];
  for (const r of rows) {
    if (!r || hcol >= r.length) continue;
    const num = r[0];
    if (num == null || !LESSON_NO.test(strip(num))) continue;
    const cell = r[hcol];
    if (cell == null || !strip(cell)) continue;
    const t = strip(cell);
    if (isWindowCell(t)) continue;
    if (t && !LESSON_NO.test(t) && !TIME_TXT.test(t)) {
      const t2 = r.length > 1 ? fmtTime(r[1]) : "";
      lessons.push((t2 ? t2 + " " : "") + t);
    }
  }
  return { lessons, found: true };
}

// ---- Матрицы из XLSX (ZIP + XML, без внешних библиотек) ----

function bytesDV(b) { return new DataView(b.buffer, b.byteOffset, b.byteLength); }
function strAt(b, off, len) { return new TextDecoder().decode(b.subarray(off, off + len)); }

async function inflateRaw(data) {
  const ds = new DecompressionStream("deflate-raw");
  const stream = new Blob([data]).stream().pipeThrough(ds);
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

// Достаёт файл из ZIP-архива (центральный каталог + локальные заголовки).
async function readZipEntry(bytes, target) {
  const n = bytes.length;
  const dv = bytesDV(bytes);
  let eocd = -1;
  for (let i = n - 22; i >= Math.max(0, n - 22 - 65535); i--) {
    if (dv.getUint32(i, true) === 0x06054b50) { eocd = i; break; }
  }
  if (eocd < 0) return null;
  const count = dv.getUint16(eocd + 10, true);
  const cdOff = dv.getUint32(eocd + 16, true);
  for (let i = 0; i < count; i++) {
    const off = cdOff + i * 46;
    if (dv.getUint32(off, true) !== 0x02014b50) continue;
    const method = dv.getUint16(off + 10, true);
    const compSize = dv.getUint32(off + 20, true);
    const nameLen = dv.getUint16(off + 28, true);
    const extraLen = dv.getUint16(off + 30, true);
    const cmtLen = dv.getUint16(off + 32, true);
    const localOff = dv.getUint32(off + 42, true);
    if (strAt(bytes, off + 46, nameLen) !== target) continue;
    const ln = dv.getUint16(localOff + 26, true);
    const le = dv.getUint16(localOff + 28, true);
    const start = localOff + 30 + ln + le;
    const comp = bytes.subarray(start, start + compSize);
    if (method === 0) return comp;                       // store
    if (method === 8) return await inflateRaw(comp);     // deflate
    return null;
  }
  return null;
}

function colToIdx(ref) {
  let col = 0;
  for (const ch of ref) {
    if (ch >= "A" && ch <= "Z") col = col * 26 + (ch.charCodeAt(0) - 64);
  }
  return col - 1;
}

function cellValue(c, shared) {
  const t = c.getAttribute("t");
  if (t === "s") {
    const v = c.getElementsByTagName("v")[0];
    if (!v) return null;
    return shared[parseInt(v.textContent || "0", 10)] ?? null;
  }
  if (t === "inlineStr") {
    const tEl = c.getElementsByTagName("t")[0];
    return tEl ? tEl.textContent : null;
  }
  if (t === "b") {
    const v = c.getElementsByTagName("v")[0];
    return v ? (v.textContent === "1" ? "TRUE" : "FALSE") : null;
  }
  const v = c.getElementsByTagName("v")[0];
  if (!v) return null;
  const s = (v.textContent || "").trim();
  if (t === "str") return s;
  if (/^-?\d+(\.\d+)?$/.test(s)) return String(parseFloat(s));
  return s;
}

function parseSheetXml(xml, shared) {
  const doc = new DOMParser().parseFromString(xml, "text/xml");
  const rowsEl = doc.getElementsByTagName("sheetData")[0];
  const rows = [];
  if (!rowsEl) return rows;
  const rowEls = rowsEl.getElementsByTagName("row");
  for (const row of rowEls) {
    const cells = row.getElementsByTagName("c");
    let maxCol = 0;
    const idxMap = new Map();
    for (const c of cells) {
      const ref = c.getAttribute("r");
      if (!ref) continue;
      const ci = colToIdx(ref.toUpperCase());
      const v = cellValue(c, shared);
      idxMap.set(ci, v == null ? null : String(v));
      if (ci > maxCol) maxCol = ci;
    }
    const rowArr = new Array(maxCol + 1).fill(null);
    for (const [k, v] of idxMap) rowArr[k] = v;
    rows.push(rowArr);
  }
  return rows;
}

function cleanRows(rows) {
  let maxcol = 0;
  for (const r of rows) {
    for (let i = r.length - 1; i >= 0; i--) if (r[i] != null && String(r[i]).trim() !== "") { if (i + 1 > maxcol) maxcol = i + 1; break; }
  }
  return rows.map((r) => (maxcol ? r.slice(0, maxcol) : r)).filter((r) => r.some((c) => c != null && String(c).trim() !== ""));
}

// Значения ячеек XLSX -> матрицы всех вкладок (как openpyxl в parse_schedule.py).
async function loadXlsxSheets(bytes) {
  const str = (name) => readZipEntry(bytes, name);
  const workbookXml = await str("xl/workbook.xml");
  const relsXml = await str("xl/_rels/workbook.xml.rels");
  if (!workbookXml) return [];
  const wb = new DOMParser().parseFromString(new TextDecoder().decode(workbookXml), "text/xml");
  const rels = new DOMParser().parseFromString(new TextDecoder().decode(relsXml || ""), "text/xml");

  const relMap = {};
  for (const rel of rels.getElementsByTagName("Relationship")) {
    const id = rel.getAttribute("Id");
    const tgt = rel.getAttribute("Target");
    if (id && tgt) relMap[id] = tgt.startsWith("/") ? tgt.replace(/^\//, "") : "xl/" + tgt;
  }

  let shared = [];
  const sstrXml = await str("xl/sharedStrings.xml");
  if (sstrXml) {
    const sd = new DOMParser().parseFromString(new TextDecoder().decode(sstrXml), "text/xml");
    for (const si of sd.getElementsByTagName("si")) shared.push(si.textContent);
  }

  const sheets = [];
  for (const sh of wb.getElementsByTagName("sheet")) {
    const name = sh.getAttribute("name") || "";
    const rid = sh.getAttribute("r:id");
    const relPath = relMap[rid];
    if (!relPath) continue;
    const sheetXml = await str(relPath);
    if (!sheetXml) continue;
    const rows = cleanRows(parseSheetXml(new TextDecoder().decode(sheetXml), shared));
    sheets.push({ name, rows });
  }
  return sheets;
}

// ---- Запасные пути (используются, только если XLSX-экспорт недоступен) ----

// gviz/tq JSONP -> матрица (без имён вкладок — полезна лишь для одиночной вкладки).
async function fetchGvizRows(sheetId, gid) {
  const q = "tqx=out:json" + (gid != null && gid !== "" ? "&gid=" + gid : "");
  const txt = await httpText("https://docs.google.com/spreadsheets/d/" + sheetId + "/gviz/tq?" + q);
  const m = /google\.visualization\.Query\.setResponse\(([\s\S]*)\)\s*;?\s*$/.exec(txt);
  if (!m) return null;
  const j = JSON.parse(m[1]);
  const rows = (j.table && j.table.rows) || [];
  const cols = (j.table && j.table.cols) || [];
  return rows.map((r) => cols.map((_, i) => {
    const c = r.c && r.c[i];
    if (!c) return null;
    const v = c.f != null ? c.f : c.v;
    return v == null ? null : String(v);
  }));
}

// htmlview -> матрица видимой вкладки.
async function fetchHtmlRows(sheetId) {
  const html = await httpText("https://docs.google.com/spreadsheets/d/" + sheetId + "/htmlview?sle=true");
  const doc = new DOMParser().parseFromString(html, "text/html");
  const rows = [];
  for (const tbl of doc.getElementsByTagName("table")) {
    for (const tr of tbl.getElementsByTagName("tr")) {
      const cells = [];
      const tds = tr.children;
      for (const td of tds) cells.push((td.textContent || "").replace(/\s+/g, " ").trim());
      if (cells.some((c) => c)) rows.push(cells);
    }
    if (rows.length) break;
  }
  return rows.length ? rows : null;
}

// Недельная разметка (row[0] = день недели) — для fallback-путей.
function weeklyFromRows(rows) {
  const days = emptyDays();
  let found = false;
  for (const r of rows) {
    if (!r || r[0] == null) continue;
    const key = dayKeyOf(String(r[0]));
    if (!key) continue;
    found = true;
    for (let i = 1; i < r.length; i++) {
      const c = r[i];
      if (c == null) continue;
      const s = strip(c);
      if (!s || s === "-" || s === "—" || s === "–" || LESSON_NO.test(s) || /^\d{1,2}\s*[.)]?\s*(урок)?$/i.test(s)) continue;
      days[key].push(s);
    }
  }
  return found ? days : null;
}

// ---- Главный обработчик /parse/google ----

async function handleParseGoogle(body) {
  const errors = [];
  const cid = String(body.cid || ""), sid = String(body.sid || ""), clid = String(body.clid || "");
  const className = String(body.className || body.class || "").trim() || "7А";
  if (!cid || !sid || !clid) return json({ updated: 0, errors: ["нет cid/sid/clid"] }, 400);

  const base = "cities/" + cid + "/schools/" + sid + "/classes/" + clid;
  const sheetId = GOOGLE_SHEETS_ID();

  // 1) Основной путь — XLSX
  let sheets = [];
  try {
    console.log("Скачиваю XLSX…");
    const bytes = await httpBytes(
      "https://docs.google.com/spreadsheets/d/" + sheetId + "/export?format=xlsx");
    if (bytes.length < 4 || bytes[0] !== 0x50 || bytes[1] !== 0x4b) {
      throw new Error("ответ Google не похож на XLSX (нет сигнатуры PK)");
    }
    console.log("Парсю вкладки XLSX…");
    sheets = await loadXlsxSheets(bytes);
  } catch (e) {
    console.error("[parse/google] xlsx:", String(e.message || e));
    errors.push("xlsx: " + String(e.message || e));
  }

  // 2) Запасные пути — gviz (одиночная вкладка) или htmlview (видимая вкладка)
  if (!sheets.length) {
    try {
      console.log("Скачиваю gviz (tqx=out:json)…");
      const rows = await fetchGvizRows(sheetId, body.gid != null ? body.gid : 0);
      if (rows) {
        const w = weeklyFromRows(rows);
        if (w) {
          const c = await fbGet(base + "/schedule");
          if (equal(c, w)) return json({ updated: 0, notes: ["gviz fallback: без изменений"] });
          await fbPut(base + "/schedule", w);
          return json({ updated: 1, notes: ["gviz fallback"] });
        }
      }
    } catch (e) {
      console.error("[parse/google] gviz:", String(e.message || e));
      errors.push("gviz: " + String(e.message || e));
    }
    try {
      console.log("Скачиваю htmlview…");
      const rows = await fetchHtmlRows(sheetId);
      if (rows) {
        const w = weeklyFromRows(rows);
        if (w) {
          const c = await fbGet(base + "/schedule");
          if (equal(c, w)) return json({ updated: 0, notes: ["htmlview fallback: без изменений"] });
          await fbPut(base + "/schedule", w);
          return json({ updated: 1, notes: ["htmlview fallback"] });
        }
      }
    } catch (e) {
      console.error("[parse/google] htmlview:", String(e.message || e));
      errors.push("htmlview: " + String(e.message || e));
    }
    console.error("[parse/google] ни XLSX, ни fallback не дали таблицу");
    return json({ updated: 0, errors: errors.length ? errors : ["Google Sheets недоступен"] }, 502);
  }

  // 3) Выбор вкладок текущей недели + колонка класса
  console.log("Выбираю вкладки текущей недели…");
  const picked = selectWeekTabs(sheets);
  if (!picked.length) {
    console.error("[parse/google] вкладки текущей недели не найдены:", sheets.map((s) => s.name).join(", "));
    return json({ updated: 0, errors: ["нет вкладок текущей недели"], tabs: sheets.map((s) => s.name) }, 502);
  }
  const byName = new Map(sheets.map((s) => [s.name, s.rows]));

  const days = emptyDays();
  let colFound = false;
  for (const p of picked) {
    console.log("Парсю вкладку «" + p.name + "»…");
    const { lessons, found } = extractClassDay(byName.get(p.name) || [], className);
    if (found) colFound = true;
    days[p.key] = lessons;
  }
  if (!colFound) {
    return json({ updated: 0, errors: ["класс «" + className + "» не найден во вкладках недели"] }, 502);
  }
  const total = HUB_KEYS.reduce((a, k) => a + days[k].length, 0);
  if (!total) return json({ updated: 0, errors: ["уроков на этой неделе нет"] }, 502);

  // 4) Сравнение с Firebase и запись ТОЛЬКО изменений
  console.log("Сравниваю с Firebase…");
  const current = await fbGet(base + "/schedule");
  if (equal(current, days)) {
    console.log("Расписание не изменилось (updated=0)");
    return json({ updated: 0 });
  }
  await fbPut(base + "/schedule", days);
  console.log("Расписание записано (updated=1)");
  return json({ updated: 1 });
}

// ============================================================================
// /parse/nikasoft — raspisanie.nikasoft.ru (var NIKA = {...})
// ============================================================================

const NIKA_URL = () =>
  Deno.env.get("NIKA_URL") || "https://raspisanie.nikasoft.ru/86111512.html";
const NIKA_DAY_SHORT = { "пн": "mon", "вт": "tue", "ср": "wed", "чт": "thu", "пт": "fri", "сб": "sat", "вс": "sun" };
const NIKA_DAY_LONG = [["mon", "понед"], ["tue", "вторн"], ["wed", "сред"], ["thu", "четверг"], ["fri", "пятниц"], ["sat", "суббот"], ["sun", "воскрес"]];
const letters = (s) => String(s).toLowerCase().replace(/[^a-zа-яё]/gi, "");

const fmtT = (s) => {
  const m = /^(\d{1,2}):(\d{1,2})/.exec(String(s));
  if (!m) return "";
  return m[1].padStart(2, "0") + ":" + m[2].padStart(2, "0");
};

async function nikaScheduleId() {
  console.log("Скачиваю HTML raspisanie.nikasoft.ru…");
  const html = await httpText(NIKA_URL());
  const m = /initial_schedule_id\s*=\s*['"]([^'"]+)['"]/.exec(html);
  if (!m) throw new Error("нет переменной initial_schedule_id");
  return m[1];
}

async function nikaLoad() {
  const id = await nikaScheduleId();
  console.log("schedule_id:", id);
  console.log("Скачиваю static/public/" + id + "…");
  let txt = await httpText("https://raspisanie.nikasoft.ru/static/public/" + id);
  txt = txt.replace(/^\ufeff/, "");
  const i = txt.indexOf("var NIKA=");
  if (i !== -1) txt = txt.slice(i + "var NIKA=".length);
  txt = txt.trim();
  if (txt.endsWith(";")) txt = txt.slice(0, -1);
  return JSON.parse(txt);
}

function nikaDayColMap(data) {
  const col = {};
  const names = data.DAY_NAMESH || data.DAY_NAMES || [];
  for (let idx = 0; idx < names.length; idx++) {
    const low = letters(names[idx]);
    if (NIKA_DAY_SHORT[low.slice(0, 2)]) { col[NIKA_DAY_SHORT[low.slice(0, 2)]] = idx; continue; }
    for (const [hk, root] of NIKA_DAY_LONG) if (low.startsWith(root)) { col[hk] = idx; break; }
  }
  return col;
}

function nikaClassId(data, className) {
  const target = normKey(className);
  for (const cid of Object.keys(data.CLASSES || {})) {
    if (normKey(data.CLASSES[cid]) === target) return cid;
  }
  return null;
}

function nikaListClasses(data) {
  const cls = data.CLASSES || {};
  const keys = Object.keys(cls).sort((a, b) => { const na = parseInt(a, 10), nb = parseInt(b, 10); return (Number.isNaN(na) ? a.localeCompare(b) : na - nb); });
  return keys.map((k) => String(cls[k]));
}

function nikaPeriodFor(data, d) {
  for (const pid of Object.keys(data.PERIODS || {})) {
    const p = data.PERIODS[pid];
    const b = parseRusDate(p && p.b), e = parseRusDate(p && p.e);
    if (b && e && d >= b && d <= e) return pid;
  }
  return null;
}

function nikaLessonText(en, subjects, rooms) {
  let s = en.s;
  if (typeof s === "string") s = [s];
  if (Array.isArray(s) && s[0] === "F") return [];
  let r = en.r;
  if (typeof r === "string") r = [r];
  const out = [];
  for (let i = 0; i < s.length; i++) {
    const sv = String(s[i] || "");
    if (sv && sv[0] === "F") continue;
    const nm = (subjects && (subjects[sv] || subjects[sv.padStart(3, "0")])) || "(нет)";
    let line = String(nm);
    if (r && i < r.length) {
      const rv = String(r[i]);
      const rm = /^\d+$/.test(rv) ? (rooms && rooms[rv.padStart(3, "0")]) : rv;
      if (rm) line += " " + rm;
    }
    out.push(line);
  }
  return out;
}

function nikaBuildWeek(data, classId, monday, sunday) {
  const dayCol = nikaDayColMap(data);
  const sched = data.CLASS_SCHEDULE || {};
  const overr = (data.CLASS_EXCHANGE || {})[classId] || {};
  const holidays = data.HOLIDAY_TRANSFER || {};
  const lessonTimes = data.LESSON_TIMES || {};
  const first = parseInt(data.FIRSTLESSONNUM, 10) || 1;
  const last = parseInt(data.LESSONSINDAY, 10) || 12;
  const subjects = data.SUBJECTS || {};
  const rooms = data.ROOMS || {};
  const cancelStr = data.LESSON_CANCELED_STR || "урок отменен";
  const days = emptyDays();

  for (let d = monday.getTime(); d <= sunday.getTime(); d += 86400000) {
    const day = new Date(d);
    const wd = (day.getUTCDay() + 6) % 7; // 0 = пн
    let hub = null, colIdx = -1;
    for (const hk of Object.keys(dayCol)) {
      if (dayCol[hk] === wd) { hub = hk; colIdx = dayCol[hk]; break; }
    }
    if (!hub) continue;
    const dateKey = fmtD(day);
    const hol = holidays[dateKey];
    if (hol && hol.type === "vacation") continue;
    const pid = nikaPeriodFor(data, day);
    if (pid == null) continue;
    const pat = ((sched[pid] || {})[classId]) || {};
    const exc = overr[dateKey] || {};
    const col = colIdx + 1;
    for (let lsn = first; lsn <= last; lsn++) {
      const en = pat[col + String(lsn).padStart(2, "0")];
      const ex = exc[String(lsn)];
      let lines = null;
      if (ex !== undefined) {
        let sxs = ex.s;
        if (typeof sxs === "string") sxs = [sxs];
        if (Array.isArray(sxs) && sxs[0] === "F") { lines = [cancelStr]; }
        else lines = nikaLessonText(ex, subjects, rooms);
      } else if (en !== undefined) {
        lines = nikaLessonText(en, subjects, rooms);
      }
      if (!lines || !lines.length) continue;
      let head = "";
      const tt = lessonTimes[String(lsn)];
      if (tt) {
        const a = fmtT(tt[0]), b = tt[1] != null ? fmtT(tt[1]) : "";
        if (a && b) head = a + "-" + b + " ";
      }
      for (const ln of lines) days[hub].push(head + ln);
    }
  }
  return days;
}

// Firebase-узел класса в конкретной школе по имени.
async function firebaseClassBySid(cid, sid, name) {
  const target = normKey(name);
  const cls = await fbGet("cities/" + cid + "/schools/" + sid + "/classes");
  if (!cls) return null;
  for (const clid of Object.keys(cls)) {
    const c = cls[clid] || {};
    if (c.name != null && normKey(c.name) === target) return clid;
  }
  return null;
}

async function handleParseNikasoft(body) {
  const errors = [];
  const cid = String(body.cid || ""), sid = String(body.sid || ""), clid = String(body.clid || "");
  if (!cid || !sid || !clid) return json({ updated: 0, errors: ["нет cid/sid/clid"] }, 400);
  const allClasses = body.allClasses === true || body.allClasses === "true";

  let data;
  try {
    data = await nikaLoad();
  } catch (e) {
    console.error("[parse/nikasoft]", String(e.message || e));
    return json({ updated: 0, errors: ["nikasoft недоступен: " + String(e.message || e)] }, 502);
  }

  const monday = weekStart(todayDate());
  const sunday = new Date(Date.UTC(monday.getUTCFullYear(), monday.getUTCMonth(), monday.getUTCDate() + 6));
  console.log("Неделя:", fmtD(monday), "—", fmtD(sunday));

  // ---- все классы или один ----
  let updated = 0;
  const base = "cities/" + cid + "/schools/" + sid + "/classes/";

  if (allClasses) {
    const names = nikaListClasses(data);
    console.log("Обрабатываю все классы (" + names.length + "):", names.join(", "));
    for (const nm of names) {
      const classId = nikaClassId(data, nm);
      if (classId == null) continue;
      const days = nikaBuildWeek(data, classId, monday, sunday);
      const total = HUB_KEYS.reduce((a, k) => a + days[k].length, 0);
      if (!total) continue;
      const fcid = await firebaseClassBySid(cid, sid, nm);
      if (!fcid) { errors.push("«" + nm + "» нет в Firebase"); continue; }
      const path = base + fcid + "/schedule";
      console.log("Парсю «" + nm + "» (" + total + " уроков), узел " + path + "…");
      const cur = await fbGet(path);
      if (equal(cur, days)) continue;
      await fbPut(path, days);
      updated++;
    }
  } else {
    const className = String(body.className || body.class || "").trim();
    const classId = className ? nikaClassId(data, className) : body.nikasoftClassId;
    if (classId == null) {
      const avail = nikaListClasses(data);
      return json({ updated: 0, errors: ["класс не найден"], available: avail.slice(0, 50) }, 502);
    }
    console.log("Парсю класс «" + className + "» (id " + classId + ")…");
    const days = nikaBuildWeek(data, classId, monday, sunday);
    const total = HUB_KEYS.reduce((a, k) => a + days[k].length, 0);
    if (!total) return json({ updated: 0, errors: ["нет расписания на эту неделю"] }, 502);

    const targetClid = clid || await firebaseClassBySid(cid, sid, className);
    if (!targetClid) return json({ updated: 0, errors: ["класс не найден в Firebase"] }, 502);
    const path = base + targetClid + "/schedule";
    console.log("Сравниваю с Firebase…");
    const cur = await fbGet(path);
    if (equal(cur, days)) {
      console.log("Расписание не изменилось (updated=0)");
      return json({ updated: 0 });
    }
    await fbPut(path, days);
    updated = 1;
  }

  console.log("Итого обновлено:", updated, errors.length ? "errors: " + errors.join("; ") : "");
  if (errors.length && !updated) return json({ updated: 0, errors }, 502);
  return json({ updated, errors: errors.length ? errors : undefined });
}

// ============================================================================
// Диспетчер
// ============================================================================

Deno.serve(async (req) => {
  const url = new URL(req.url);
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors() });
  if (url.pathname !== "/moderate" && url.pathname !== "/parse/google" && url.pathname !== "/parse/nikasoft") {
    if (req.method === "GET" && (url.pathname === "/" || url.pathname === "/health")) {
      return json({ ok: true, endpoints: ["/moderate", "/parse/google", "/parse/nikasoft"] });
    }
    return json({ error: "not_found" }, 404);
  }
  if (req.method !== "POST") return json({ error: "method_not_allowed" }, 405);
  let body;
  try { body = await req.json(); } catch { return json({ error: "invalid_json" }, 400); }

  try {
    if (url.pathname === "/moderate") return await handleModerate(body);
    if (url.pathname === "/parse/google") return await handleParseGoogle(body);
    return await handleParseNikasoft(body);
  } catch (e) {
    console.error("Unhandled:", String(e && e.stack || e));
    return json({ updated: 0, errors: ["internal: " + String(e.message || e)] }, 500);
  }
});