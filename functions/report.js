function normalizeDate(input) {
  const match = String(input || "").match(/^(20\d{2})[/-](\d{1,2})[/-](\d{1,2})$/);
  if (!match) return null;
  const [, year, month, day] = match;
  return `${year}-${month.padStart(2, "0")}-${day.padStart(2, "0")}`;
}

function compactDate(date) {
  return date.replaceAll("-", "");
}

function slashDate(date) {
  return date.replaceAll("-", "/");
}

function toNumber(value) {
  return Number(String(value || "0").replaceAll(",", "").trim()) || 0;
}

function lots(value) {
  return Math.round(toNumber(value) / 1000);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function fetchT86(date) {
  const url = `https://www.twse.com.tw/rwd/zh/fund/T86?date=${compactDate(date)}&selectType=ALLBUT0999&response=json`;
  const response = await fetch(url);
  if (!response.ok) return { ok: false, reason: `TWSE ${response.status}` };
  const json = await response.json();
  if (json.stat !== "OK" || !Array.isArray(json.data)) {
    return { ok: false, reason: json.stat || "資料不足" };
  }
  const fields = json.fields || [];
  const rows = json.data.map((row) => Object.fromEntries(fields.map((field, index) => [field, row[index]])));
  return { ok: true, rows, title: json.title || "" };
}

function topRows(rows, column, desc = true) {
  return [...rows]
    .sort((a, b) => {
      const av = toNumber(a[column]);
      const bv = toNumber(b[column]);
      return desc ? bv - av : av - bv;
    })
    .slice(0, 10)
    .map((row) => ({
      code: row["證券代號"],
      name: String(row["證券名稱"] || "").trim(),
      lots: lots(row[column])
    }));
}

function tablePair(title, buyRows, sellRows) {
  const body = Array.from({ length: 10 }, (_, index) => {
    const buy = buyRows[index] || {};
    const sell = sellRows[index] || {};
    return `<tr>
      <td>${index + 1}</td>
      <td>${escapeHtml(buy.name || "")} ${escapeHtml(buy.code || "")}</td>
      <td class="pos">${buy.lots ?? ""}</td>
      <td>${escapeHtml(sell.name || "")} ${escapeHtml(sell.code || "")}</td>
      <td class="neg">${sell.lots ?? ""}</td>
    </tr>`;
  }).join("");
  return `<h3>${escapeHtml(title)}</h3>
    <table>
      <thead><tr><th>排名</th><th>買超</th><th>張數</th><th>賣超</th><th>張數</th></tr></thead>
      <tbody>${body}</tbody>
    </table>`;
}

function renderHtml({ date, t86 }) {
  const dateText = slashDate(date);
  let content = "";

  if (!t86.ok) {
    content = `<section>
      <h2>資料狀態</h2>
      <p>目前無法取得 ${dateText} 的證交所三大法人買賣超資料。</p>
      <p>可能原因：該日休市、尚未公布、或公開資料來源暫時無法取得。</p>
      <div class="note">資料狀態：${escapeHtml(t86.reason)}</div>
    </section>`;
  } else {
    const rows = t86.rows;
    const foreignCol = "外陸資買賣超股數(不含外資自營商)";
    const trustCol = "投信買賣超股數";
    const dealerCol = "自營商買賣超股數";
    const totalCol = "三大法人買賣超股數";
    const foreignBuy = topRows(rows, foreignCol, true);
    const foreignSell = topRows(rows, foreignCol, false);
    const trustBuy = topRows(rows, trustCol, true);
    const trustSell = topRows(rows, trustCol, false);
    const dealerBuy = topRows(rows, dealerCol, true);
    const dealerSell = topRows(rows, dealerCol, false);
    const totalBuy = topRows(rows, totalCol, true);
    const totalSell = topRows(rows, totalCol, false);

    content = `<section>
      <h2>今日市場結論</h2>
      <ul>
        <li>這份報告依 ${dateText} 的證交所法人買賣超資料產生。</li>
        <li>若該日期為盤後資料，重點先看三大法人合計方向與外資是否集中買賣權值股或 ETF。</li>
        <li>買賣超只能代表籌碼方向，仍需搭配價格、成交量、產業趨勢與國際市場判斷。</li>
      </ul>
      <div class="note">${escapeHtml(t86.title)}</div>
    </section>

    <section>
      <h2>法人買賣超總表</h2>
      ${tablePair("外資買超 / 賣超前 10", foreignBuy, foreignSell)}
      ${tablePair("投信買超 / 賣超前 10", trustBuy, trustSell)}
      ${tablePair("自營商買超 / 賣超前 10", dealerBuy, dealerSell)}
      ${tablePair("三大法人合計買超 / 賣超前 10", totalBuy, totalSell)}
    </section>

    <section>
      <h2>ETF 00981A / 00403A 觀察</h2>
      <p>若 00981A 或 00403A 出現在法人買賣超前段，代表主動式 ETF 當日籌碼變化需要特別追蹤。</p>
      <p>成分股權重屬 ETF 發行商資料，歷史權重若無公開快照，需以發行商當日資料為準，本文不臆測權重。</p>
    </section>`;
  }

  return `<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>台股日期報告 ${dateText}</title>
  <style>
    :root{--paper:#F4F0E8;--panel:#FFFDF8;--soft:#F9F6EE;--ink:#1F252B;--muted:#706B63;--line:#C8BFAE;--charcoal:#252A2F;--teal:#236B68;--wine:#8B3F42;--ochre:#B9852E;--red:#B64B4B;--green:#2F7D5B}
    *{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font-family:"Microsoft JhengHei","Noto Sans TC",Arial,sans-serif;line-height:1.65}.wrap{max-width:1120px;margin:auto;padding:28px 20px 60px}
    header{background:var(--panel);border:1px solid var(--line);border-radius:18px;overflow:hidden;display:grid;grid-template-columns:220px 1fr}.brand{background:var(--charcoal);color:white;padding:30px;border-left:8px solid var(--wine);position:relative}.brand:after{content:"";position:absolute;right:0;top:0;width:9px;height:100%;background:var(--teal)}
    .brand h1{font-size:25px;line-height:1.16;margin:0}.brand p{margin-top:90px;color:#d6d0c4}.intro{padding:34px 42px}.intro h2{font-size:31px;line-height:1.16;margin:0 0 12px}.rule{width:250px;height:3px;background:var(--ochre);margin:20px 0}
    section{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:24px;margin-top:18px}h2{font-size:23px;margin:0 0 12px}h3{font-size:17px;margin:22px 0 8px;color:var(--teal)}
    table{width:100%;border-collapse:separate;border-spacing:0;border:1px solid var(--line);border-radius:12px;overflow:hidden;font-size:14px;margin-top:10px}th{background:var(--charcoal);color:white;text-align:left;padding:10px 12px;white-space:nowrap}td{background:#fff;padding:10px 12px;border-top:1px solid #e7dece;vertical-align:top}tr:nth-child(even) td{background:#fbf8f0}
    .pos{color:var(--green);font-weight:700}.neg{color:var(--red);font-weight:700}.note{background:var(--soft);border:1px solid var(--line);border-left:6px solid var(--ochre);border-radius:12px;padding:14px 16px;margin-top:14px}.muted{color:var(--muted)}
    @media(max-width:840px){.wrap{padding:18px 12px 48px}header{grid-template-columns:1fr}.brand p{margin-top:42px}.intro{padding:26px 22px}.intro h2{font-size:26px}section{padding:18px}table{font-size:13px}th,td{padding:9px 8px}}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div class="brand"><h1>台股日期<br>報告</h1><p>${dateText}</p></div>
      <div class="intro">
        <h2>${dateText} 台股報告</h2>
        <div class="rule"></div>
        <p class="muted">本頁依你指定日期產生。若該日休市或公開資料不足，會直接標示，不會硬編資料。</p>
      </div>
    </header>
    ${content}
    <section><h2>風險提醒</h2><p>本報告為研究與決策輔助，非投資建議或獲利保證。歷史法人買賣超不代表未來股價方向。</p></section>
  </div>
</body>
</html>`;
}

export async function onRequestGet({ request }) {
  const url = new URL(request.url);
  const date = normalizeDate(url.searchParams.get("date"));
  if (!date) {
    return new Response("Missing or invalid date. Use /report?date=YYYY-MM-DD", { status: 400 });
  }
  const t86 = await fetchT86(date);
  return new Response(renderHtml({ date, t86 }), {
    headers: { "Content-Type": "text/html; charset=utf-8" }
  });
}
