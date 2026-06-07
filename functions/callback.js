const REPORT_URL = "https://taiwan-stock-report-16l.pages.dev/";
const REPORT_LABEL = "2026/06/08 盤前觀察版";
const MARKET_RESULT_DATE = "2026/06/05 最近交易日";

function extractDate(text) {
  if (!text) return null;
  const match = String(text).match(/\b(20\d{2})[\/-](\d{1,2})[\/-](\d{1,2})\b/);
  if (!match) return null;
  const [, year, month, day] = match;
  return `${year}-${month.padStart(2, "0")}-${day.padStart(2, "0")}`;
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
    const slashDate = date.replaceAll("-", "/");
    return [
      `這份是 ${slashDate} 的台股日期報告。`,
      "",
      "我會依你指定的日期產生頁面；若當天沒有開盤，頁面會顯示無交易資料與原因。",
      "",
      `點這裡看：${REPORT_URL}report?date=${date}`,
      "",
      "提醒：內容為研究與決策輔助，不保證投資報酬。"
    ].join("\n");
  }

  return [
    "這份是最新台股晨報。",
    "",
    `報告版本：${REPORT_LABEL}`,
    `市場資料：${MARKET_RESULT_DATE}`,
    "",
    `點這裡看：${REPORT_URL}`,
    "",
    "提醒：內容為研究與決策輔助，不保證投資報酬。"
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
  return new Response("LINE callback is active.");
}
