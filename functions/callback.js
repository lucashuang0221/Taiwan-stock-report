const REPORT_URL = "https://taiwan-stock-report-16l.pages.dev/";
const LATEST_REPORT_DATE = "2026/06/08";

function extractDate(text) {
  if (!text) return null;
  const match = String(text).match(/\b(20\d{2})[\/-](\d{1,2})[\/-](\d{1,2})\b/);
  if (!match) return null;
  const [, year, month, day] = match;
  return `${year}-${month.padStart(2, "0")}-${day.padStart(2, "0")}`;
}

function slashDate(date) {
  return date.replaceAll("-", "/");
}

function shouldReply(text) {
  if (!text) return false;
  if (extractDate(text)) return true;
  const normalized = text.toLowerCase();
  return [
    "台股",
    "台股報告",
    "台股晨報",
    "今日台股",
    "台股分析",
    "法人買賣超",
    "外資買賣超",
    "00981a",
    "00403a",
    "etf"
  ].some((keyword) => normalized.includes(keyword));
}

async function buildReply(text) {
  const date = extractDate(text);
  if (date) {
    const displayDate = slashDate(date);
    return `這份是 ${displayDate} 的台股日期報告。\n${REPORT_URL}report?date=${date}`;
  }

  return `這份是 ${LATEST_REPORT_DATE} 的台股日期報告。\n${REPORT_URL}`;
}

async function replyToLine(replyToken, text, env) {
  const token = env.LINE_CHANNEL_ACCESS_TOKEN;
  if (!token) {
    return new Response("Missing LINE_CHANNEL_ACCESS_TOKEN", { status: 500 });
  }

  const response = await fetch("https://api.line.me/v2/bot/message/reply", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json; charset=utf-8"
    },
    body: JSON.stringify({
      replyToken,
      messages: [{ type: "text", text }]
    })
  });

  if (!response.ok) {
    const body = await response.text();
    return new Response(`LINE reply failed: ${response.status} ${body}`, { status: 500 });
  }

  return new Response("OK");
}

export async function onRequestPost({ request, env }) {
  const payload = await request.json();
  const events = payload.events || [];

  for (const event of events) {
    const text = event.message?.type === "text" ? event.message.text : "";
    if (event.replyToken && shouldReply(text)) {
      return replyToLine(event.replyToken, await buildReply(text), env);
    }
  }

  return new Response("No matching message");
}

export async function onRequestGet() {
  return new Response("LINE callback is active.");
}
