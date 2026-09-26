// Cloudflare Worker: прокси-модерация для xKiro (обход CORS).
//
//   POST   /moderate  — тело JSON { text, nick, model? } -> JSON { bad, category, reason }
//   OPTIONS /moderate — preflight -> 204 с CORS-заголовками
//
// Ключ xKiro НЕ хранится в клиенте: читается из env.XKIRO_API_KEY
// (задаётся через `wrangler secret put XKIRO_API_KEY` или в панели Cloudflare).

const XKIRO_URL = "https://api.xkiro.com/v1/chat/completions";
const DEFAULT_MODEL = "qwen/qwen3.6-plus:free";
// "*" для любых фронтов или строго свой домен: "https://schoolhub-dev.github.io"
const CORS_ORIGIN = "*";

const SYSTEM_PROMPT =
  'Ты строгий модератор школьного чата. Определи, нарушает ли сообщение правила: ' +
  'мат (в т.ч. замаскированный: замена букв символами, латиницей, перестановка, ' +
  '"квас", "хрю", буквы-заглушки), оскорбление, травля, угрозы, грубость, спам/реклама, ' +
  'попытка обойти фильтр. Отвечай ТОЛЬКО валидным JSON: ' +
  '{"bad": true или false, "category": "мат|оскорбление|травля|угрозы|спам|другое|none", ' +
  '"reason": "краткая причина или пустая строка"}.';

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // Preflight
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders() });
    }

    if (request.method !== "POST" || url.pathname !== "/moderate") {
      return json({ error: "not_found" }, 404);
    }

    if (!env.XKIRO_API_KEY) {
      return json({ error: "XKIRO_API_KEY not configured" }, 500);
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return json({ error: "invalid_json" }, 400);
    }

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
        { role: "user", content: "Сообщение для проверки (ник: @" + nick + "):\n" + text }
      ]
    };

    const sendOpt = (extra) => fetch(XKIRO_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + env.XKIRO_API_KEY
      },
      body: JSON.stringify(Object.assign({}, payload, extra || {}))
    });

    let upstream;
    try {
      upstream = await sendOpt({ response_format: { type: "json_object" } });
    } catch (e) {
      return json({ error: "upstream_network_error", message: String(e.message || e) }, 502);
    }
    if (upstream.status === 400) {
      // Некоторые модели не принимают response_format — пробуем без него
      try {
        upstream = await sendOpt(null);
      } catch (e) {
        return json({ error: "upstream_network_error", message: String(e.message || e) }, 502);
      }
    }

    let bodyText = "";
    try {
      bodyText = await upstream.text();
    } catch (e) { /* тело недоступно */ }
    console.log("xKiro status:", upstream.status);
    console.log("xKiro body:", bodyText);
    let data = null;
    try {
      data = JSON.parse(bodyText);
    } catch { /* не JSON */ }

    const content = (data && data.choices && data.choices[0] && data.choices[0].message && data.choices[0].message.content) || "";
    const block = content.match(/\{[\s\S]*\}/);

    if (upstream.ok && block) {
      try {
        const j = JSON.parse(block[0]);
        if (typeof j.bad === "boolean") {
          return json({
            bad: j.bad,
            category: String(j.category || "").slice(0, 30),
            reason: String(j.reason || "").slice(0, 80)
          });
        }
      } catch { /* ниже */ }
    }

    const detail = (data && data.error && (data.error.message || JSON.stringify(data.error))) || content.slice(0, 300);
    return json({ error: "upstream_response", status: upstream.status, detail }, 502);
  }
};

function corsHeaders() {
  return {
    "Access-Control-Allow-Origin": CORS_ORIGIN,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
    "Content-Type": "application/json"
  };
}

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), { status, headers: corsHeaders() });
}