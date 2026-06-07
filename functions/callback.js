const REPORT_URL = "https://taiwan-stock-report-16l.pages.dev/";
const REPORT_LABEL = "2026/06/07 週日盤前觀察版";
const MARKET_RESULT_DATE = "2026/06/05 最近交易日";

function extractDate(text) {
  if (!text) return false;
  const normalized = text.toLowerCase();
  const match = normalized.match(/\b(20\d{2})[\/-](\d{1,2})[\/-](\d{1,2})\b/);
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
    "股市報告",
    "00981a",
    "00403a",
    "etf成分股",
    "etf 成分股",
    "法人買賣超",
    "外資買賣超"
  ].some((keyword) => normalized.includes(keyword.toLowerCase()));
}

async function reportExists(date) {
  const url = `${REPORT_URL}reports/${date}.html`;
  const response = await fetch(url, { method: "HEAD" });
  return response.ok;
}

async function buildReply(text) {
  const date = extractDate(text);
  if (date) {
    if (await reportExists(date)) {
      const slashDate = date.replaceAll("-", "/");
      return `台股報告已找到。\n\n這份是 ${slashDate} 的台股報告。\n\n點擊查看：\n${REPORT_URL}reports/${date}.html\n\n提醒：內容為研究與決策輔助，非投資報酬保證。`;
    }
    const slashDate = date.replaceAll("-", "/");
    return `目前沒有 ${slashDate} 的台股報告。\n\n你可以輸入「台股」查看最新報告：\n${REPORT_URL}`;
  }

  return `台股晨報已整理好。\n\n這份是 ${REPORT_LABEL}，內容採用 ${MARKET_RESULT_DATE} 的台股結果、法人買賣超與 00981A / 00403A ETF 觀察。\n\n點擊查看：\n${REPORT_URL}\n\n提醒：內容為研究與決策輔助，非投資報酬保證。`;
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
