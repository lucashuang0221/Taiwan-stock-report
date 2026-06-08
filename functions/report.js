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

function findField(fields, keywords) {
  return fields.find((field) => keywords.every((keyword) => field.includes(keyword)));
}

async function fetchT86(date) {
  const url = `https://www.twse.com.tw/rwd/zh/fund/T86?date=${compactDate(date)}&selectType=ALLBUT0999&response=json`;
  const response = await fetch(url);
  if (!response.ok) return { ok: false, reason: `TWSE ${response.status}` };
  const json = await response.json();
  if (json.stat !== "OK" || !Array.isArray(json.data)) {
    return { ok: false, reason: json.stat || "查無當日法人資料" };
  }
  const fields = json.fields || [];
  const rows = json.data.map((row) => Object.fromEntries(fields.map((field, index) => [field, row[index]])));
  return { ok: true, rows, fields, title: json.title || "" };
}

function topRows(rows, column, desc = true) {
  if (!column) return [];
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

  return `<div class="table-block">
    <h3>${escapeHtml(title)}</h3>
    <div class="tw">
      <table>
        <thead><tr><th>排名</th><th>買超標的</th><th>張數</th><th>賣超標的</th><th>張數</th></tr></thead>
        <tbody>${body}</tbody>
      </table>
    </div>
  </div>`;
}

function kpiCards({ date, status }) {
  return `<div class="kpi4">
    <div class="kcard"><div class="kl">報告日期</div><div class="kval vb">${slashDate(date)}</div><div class="kch">依使用者指定日期產生</div></div>
    <div class="kcard"><div class="kl">資料來源</div><div class="kval vg">TWSE</div><div class="kch">三大法人買賣超</div></div>
    <div class="kcard"><div class="kl">內容型態</div><div class="kval va">LINE View</div><div class="kch">手機點開可直接閱讀</div></div>
    <div class="kcard"><div class="kl">資料狀態</div><div class="kval ${status === "ok" ? "vg" : "vr"}">${status === "ok" ? "可讀取" : "無交易"}</div><div class="kch">遇假日會提示原因</div></div>
  </div>`;
}

function renderHtml({ date, t86 }) {
  const dateText = slashDate(date);
  let body = "";

  if (!t86.ok) {
    body = `<section class="sec">
      <div class="sh"><div class="si">!</div><div class="st">資料狀態</div><span class="stag tr">無當日交易資料</span></div>
      <div class="bod">
        ${kpiCards({ date, status: "empty" })}
        <div class="alert al-amber">
          <strong>${dateText} 目前查不到台股三大法人交易資料。</strong>
          可能原因是週末、國定假日、交易所尚未發布資料，或該日期非台股交易日。
        </div>
        <ul class="slist">
          <li><span class="arr-a">1</span><div><strong>建議動作：</strong>改查最近一個台股交易日，或等交易所資料發布後再重新開啟本頁。</div></li>
          <li><span class="arr-b">2</span><div><strong>LINE 使用方式：</strong>直接輸入日期，例如 2026/5/29，系統會產生該日期頁面。</div></li>
          <li><span class="arr-r">3</span><div><strong>風險提醒：</strong>沒有交易資料時，不應推論法人方向或個股強弱。</div></li>
        </ul>
        <div class="note">資料狀態：${escapeHtml(t86.reason)}</div>
      </div>
    </section>`;
  } else {
    const rows = t86.rows;
    const fields = t86.fields || [];
    const foreignCol = findField(fields, ["外資", "買賣超", "不含"]);
    const trustCol = findField(fields, ["投信", "買賣超"]);
    const dealerCol = findField(fields, ["自營商", "買賣超", "合計"]) || findField(fields, ["自營商", "買賣超"]);
    const totalCol = findField(fields, ["三大法人", "買賣超"]);

    const foreignBuy = topRows(rows, foreignCol, true);
    const foreignSell = topRows(rows, foreignCol, false);
    const trustBuy = topRows(rows, trustCol, true);
    const trustSell = topRows(rows, trustCol, false);
    const dealerBuy = topRows(rows, dealerCol, true);
    const dealerSell = topRows(rows, dealerCol, false);
    const totalBuy = topRows(rows, totalCol, true);
    const totalSell = topRows(rows, totalCol, false);

    body = `<section class="sec">
      <div class="sh"><div class="si">01</div><div class="st">今日市場結論</div><span class="stag tb">法人籌碼觀察</span></div>
      <div class="bod">
        ${kpiCards({ date, status: "ok" })}
        <ul class="slist">
          <li><span class="arr-b">1</span><div><strong>${dateText} 的核心資料以 TWSE 三大法人買賣超為主。</strong>先看外資、投信、自營商是否同向，判斷資金是否集中或分歧。</div></li>
          <li><span class="arr-g">2</span><div><strong>買超榜用來找主流資金方向。</strong>若買超集中在 AI、半導體、金融或高股息 ETF，代表資金偏好明確。</div></li>
          <li><span class="arr-r">3</span><div><strong>賣超榜用來看降溫壓力。</strong>若權值股或 ETF 同步出現在賣超前十，短線容易造成指數壓力。</div></li>
          <li><span class="arr-a">4</span><div><strong>本頁先提供可直接閱讀的日期版報告。</strong>若要完整晨報，可再延伸加入國際盤、技術線型、ETF 成分股與策略配置。</div></li>
        </ul>
        <div class="note">${escapeHtml(t86.title)}</div>
      </div>
    </section>

    <section class="sec">
      <div class="sh"><div class="si">02</div><div class="st">法人買賣超前 10 名</div><span class="stag tg">外資 / 投信 / 自營商</span></div>
      <div class="bod">
        ${tablePair("外資買超 / 賣超前 10", foreignBuy, foreignSell)}
        ${tablePair("投信買超 / 賣超前 10", trustBuy, trustSell)}
        ${tablePair("自營商買超 / 賣超前 10", dealerBuy, dealerSell)}
        ${tablePair("三大法人合計買超 / 賣超前 10", totalBuy, totalSell)}
      </div>
    </section>

    <section class="sec">
      <div class="sh"><div class="si">03</div><div class="st">ETF 00981A / 00403A 觀察</div><span class="stag ta">每日追蹤</span></div>
      <div class="bod">
        <div class="clist">
          <div class="card">
            <div class="ctop"><span class="badge bb">00981A</span><span class="cname">主動式台股 ETF 觀察</span></div>
            <p>若 00981A 的成分股或關聯權值股出現在法人賣超前段，代表短線可能受到高檔調節影響；若法人轉買且量能回升，才視為重新轉強訊號。</p>
          </div>
          <div class="card">
            <div class="ctop"><span class="badge bg">00403A</span><span class="cname">主動式台股 ETF 觀察</span></div>
            <p>00403A 需同步觀察 AI、半導體與大型權值股走勢。若買超集中但價格未突破，代表資金可能仍在布局，不宜直接追高。</p>
          </div>
        </div>
        <div class="alert al-blue">
          <strong>ETF 成分股提醒</strong>
          本日期頁以交易所法人買賣超為核心。ETF 即時成分股、權重與申購買回狀態仍需以發行商最新揭露為準。
        </div>
      </div>
    </section>`;
  }

  return `<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
  <title>台股日期報告 ${dateText}</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700;900&display=swap');
    :root{--navy:#0F172A;--blue:#38BDF8;--light:#F8FAFC;--border:#E2E8F0;--muted:#64748B;--up:#10B981;--down:#EF4444;--warn:#F59E0B;--text:#1E293B;}
    *{box-sizing:border-box;margin:0;padding:0;}
    body{font-family:'Noto Sans TC','Microsoft JhengHei',sans-serif;font-size:14px;color:var(--text);background:#F1F5F9;line-height:1.6;}
    .header{background:linear-gradient(135deg,#1C1917 0%,#292524 50%,#44403C 100%);padding:20px 16px 16px;}
    .hbadge{display:inline-block;font-size:10px;font-weight:700;letter-spacing:1.5px;padding:3px 10px;border-radius:20px;background:rgba(56,189,248,.18);color:#BAE6FD;border:1px solid rgba(56,189,248,.38);margin-bottom:8px;}
    .htitle{font-size:23px;font-weight:900;color:white;line-height:1.2;margin-bottom:4px;}
    .hsub{font-size:11px;color:rgba(255,255,255,.62);margin-bottom:16px;}
    .kg{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;}
    .kv{display:flex;flex-direction:column;}
    .kv .lbl{font-size:9px;color:rgba(255,255,255,.45);letter-spacing:.5px;margin-bottom:2px;}
    .kv .val{font-size:13px;font-weight:700;}
    .vr{color:#F87171;}.vg{color:#6EE7B7;}.vb{color:#7DD3FC;}.va{color:#FDE68A;}
    .drama-bar{background:var(--navy);border-bottom:3px solid var(--warn);padding:13px 16px;}
    .db-label{font-size:10px;font-weight:700;letter-spacing:2px;color:var(--warn);margin-bottom:6px;}
    .db-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;}
    .dcard{border-radius:8px;padding:9px 10px;text-align:center;}
    .dcard.act1{background:rgba(16,185,129,.15);border:1px solid rgba(16,185,129,.3);}
    .dcard.act2{background:rgba(239,68,68,.15);border:1px solid rgba(239,68,68,.3);}
    .dcard.act3{background:rgba(56,189,248,.15);border:1px solid rgba(56,189,248,.3);}
    .dcard .dt{font-size:9px;color:rgba(255,255,255,.55);margin-bottom:3px;}
    .dcard .dv{font-size:12px;font-weight:700;color:white;line-height:1.35;}
    .sec{background:white;margin:10px 10px 0;border-radius:12px;border:1px solid var(--border);overflow:hidden;}
    .sh{display:flex;align-items:center;gap:8px;padding:12px 14px;border-bottom:2px solid var(--navy);background:var(--light);}
    .si{min-width:28px;height:28px;background:var(--navy);color:white;border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:900;flex-shrink:0;padding:0 5px;}
    .st{font-size:14px;font-weight:700;color:var(--navy);flex:1;}
    .stag{font-size:10px;font-weight:700;padding:2px 8px;border-radius:20px;white-space:nowrap;}
    .tr{background:#FEE2E2;color:#991B1B;}.tg{background:#D1FAE5;color:#065F46;}.tb{background:#E0F2FE;color:#075985;}.ta{background:#FEF3C7;color:#92400E;}
    .bod{padding:14px;}
    .slist{list-style:none;}
    .slist li{display:flex;gap:10px;padding:9px 0;border-bottom:1px solid #F1F5F9;font-size:13px;line-height:1.65;}
    .slist li:last-child{border-bottom:none;}
    .arr-g,.arr-r,.arr-a,.arr-b{font-weight:900;font-size:13px;flex-shrink:0;margin-top:1px;border-radius:6px;width:24px;height:24px;text-align:center;line-height:24px;color:white;}
    .arr-g{background:var(--up);}.arr-r{background:var(--down);}.arr-a{background:var(--warn);}.arr-b{background:var(--blue);}
    .kpi4{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-bottom:12px;}
    .kcard{background:var(--light);border-radius:8px;padding:10px 12px;border:1px solid var(--border);}
    .kcard .kl{font-size:10px;color:var(--muted);margin-bottom:3px;}
    .kcard .kval{font-size:18px;font-weight:700;line-height:1.1;}
    .kcard .kch{font-size:10px;margin-top:3px;font-weight:600;color:var(--muted);}
    .tw{overflow-x:auto;-webkit-overflow-scrolling:touch;}
    .table-block{margin-top:14px;}
    table{width:100%;border-collapse:collapse;font-size:12px;min-width:460px;}
    thead tr{background:var(--navy);color:white;}
    thead th{padding:8px 10px;text-align:left;font-weight:700;font-size:11px;white-space:nowrap;}
    tbody tr{border-bottom:1px solid var(--border);}
    tbody tr:nth-child(even){background:var(--light);}
    tbody td{padding:8px 10px;vertical-align:top;font-size:12px;line-height:1.5;}
    h3{font-size:13px;color:var(--navy);margin:0 0 7px;}
    p{font-size:13px;color:var(--text);line-height:1.7;}
    .pos{color:var(--up);font-weight:700}.neg{color:var(--down);font-weight:700}
    .clist{display:flex;flex-direction:column;gap:10px;}
    .card{border:1px solid var(--border);border-radius:10px;padding:12px;}
    .ctop{display:flex;align-items:center;gap:8px;margin-bottom:6px;}
    .cname{font-size:13px;font-weight:700;color:var(--navy);flex:1;}
    .badge{display:inline-block;font-size:10px;font-weight:700;padding:2px 8px;border-radius:20px;}
    .bb{background:#E0F2FE;color:#0369A1;}.bg{background:#D1FAE5;color:#065F46;}
    .alert,.note{padding:11px 13px;border-radius:8px;font-size:12px;line-height:1.7;margin-top:12px;}
    .alert strong{font-size:13px;display:block;margin-bottom:4px;}
    .al-amber{background:#FFFBEB;border-left:4px solid var(--warn);color:#78350F;}
    .al-blue{background:#EFF6FF;border-left:4px solid var(--blue);color:#1E3A5F;}
    .note{background:#F8FAFC;border-left:4px solid var(--navy);color:var(--muted);}
    .footer{text-align:center;font-size:10px;color:var(--muted);margin:10px 10px 20px;padding:12px;background:white;border-radius:10px;border:1px solid var(--border);line-height:1.8;}
  </style>
</head>
<body>
  <div class="header">
    <div class="hbadge">TAIWAN MARKET REPORT · ${dateText}</div>
    <div class="htitle">台股日期報告</div>
    <div class="hsub">依指定日期產生，重點整理法人買賣超、ETF 觀察與風險提醒。</div>
    <div class="kg">
      <div class="kv"><span class="lbl">日期</span><span class="val vb">${dateText}</span></div>
      <div class="kv"><span class="lbl">資料</span><span class="val vg">TWSE 法人</span></div>
      <div class="kv"><span class="lbl">閱讀</span><span class="val va">LINE / 手機</span></div>
      <div class="kv"><span class="lbl">重點</span><span class="val vb">前 10 名</span></div>
      <div class="kv"><span class="lbl">ETF</span><span class="val vg">00981A / 00403A</span></div>
      <div class="kv"><span class="lbl">風險</span><span class="val vr">不追高</span></div>
    </div>
  </div>

  <div class="drama-bar">
    <div class="db-label">今日閱讀順序</div>
    <div class="db-grid">
      <div class="dcard act1"><div class="dt">第一步</div><div class="dv">先看法人<br>是否同向</div></div>
      <div class="dcard act2"><div class="dt">第二步</div><div class="dv">再看賣超<br>壓力來源</div></div>
      <div class="dcard act3"><div class="dt">第三步</div><div class="dv">最後判斷<br>ETF 風險</div></div>
    </div>
  </div>

  ${body}

  <div class="footer">
    台股日期報告 ${dateText}<br>
    本內容為研究與決策輔助，不保證投資報酬。資料以 TWSE 與發行商最新揭露為準。
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

  const archivedUrl = new URL(`/reports/${date}`, request.url);
  const archived = await fetch(archivedUrl);
  if (archived.ok) {
    const html = await archived.text();
    return new Response(html, {
      headers: { "Content-Type": "text/html; charset=utf-8" }
    });
  }

  const t86 = await fetchT86(date);
  return new Response(renderHtml({ date, t86 }), {
    headers: { "Content-Type": "text/html; charset=utf-8" }
  });
}
