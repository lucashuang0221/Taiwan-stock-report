const REPORT_BASE_URL = "https://taiwan-stock-report-16l.pages.dev";

function normalizeDateParts(year, month, day) {
  return `${year}-${month.padStart(2, "0")}-${day.padStart(2, "0")}`;
}

function extractDate(text) {
  if (!text) return null;

  const source = String(text);
  const fullDate = source.match(/\b(20\d{2})[./-](\d{1,2})[./-](\d{1,2})\b/);
  if (fullDate) {
    return normalizeDateParts(fullDate[1], fullDate[2], fullDate[3]);
  }

  const zhDate = source.match(/\b(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?\b/);
  if (zhDate) {
    return normalizeDateParts(zhDate[1], zhDate[2], zhDate[3]);
  }

  return null;
}

function slashDate(date) {
  return date.replaceAll("-", "/");
}

function reportUrlForDate(date) {
  return `${REPORT_BASE_URL}/report?date=${date}`;
}

function shouldReply(text) {
  if (!text) return false;
  if (extractDate(text)) return true;

  const normalized = String(text).toLowerCase();
  return [
    "台股",
    "晨報",
    "台股晨報",
    "法人",
    "外資",
    "投信",
    "自營商",
    "00981a",
    "00403a",
    "etf"
  ].some((keyword) => normalized.includes(keyword));
}

async function buildReply(text) {
  const date = extractDate(text);
  if (!date) {
    return "請指定報表日期，例如：台股晨報 2026-06-12";
  }

  return [
    `已收到指定日期：${slashDate(date)}`,
    "報表會依這個日期產出；若該日台股未開盤，內容會以最近可取得的市場資料作為基準。",
    reportUrlForDate(date)
  ].join("\n");
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
  return new Response("LINE callback is active. Send a message with a date, for example: 台股晨報 2026-06-12");
}
