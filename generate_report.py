from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PUBLIC_URL = "https://taiwan-stock-report-16l.pages.dev/"
REPORT_DATE = ""
MARKET_RESULT_DATE = ""


def fetch_json(url: str) -> dict:
    last_error = None
    for _ in range(3):
        result = subprocess.run(
            ["curl.exe", "-L", "-s", url],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            last_error = exc
    raise RuntimeError(f"Invalid JSON response from {url}: {last_error}")


def fetch_text(url: str) -> str:
    result = subprocess.run(
        ["curl.exe", "-L", "-s", url],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )
    return result.stdout


def to_int(text: str) -> int:
    return int(str(text).replace(",", "").strip() or "0")


def to_float(text: str) -> float:
    return float(str(text).replace(",", "").replace("%", "").strip() or "0")


def normalize_date(value: str) -> str:
    return date.fromisoformat(value.replace("/", "-")).isoformat()


def twse_mi_index_url(market_date: str) -> str:
    return (
        "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
        f"?date={market_date.replace('-', '')}&type=ALLBUT0999&response=json"
    )


def resolve_market_result_date(report_date: str, explicit_market_date: str | None) -> str:
    if explicit_market_date:
        return normalize_date(explicit_market_date)

    cursor = date.fromisoformat(report_date)
    for _ in range(10):
        candidate = cursor.isoformat()
        try:
            data = fetch_json(twse_mi_index_url(candidate))
        except Exception:
            data = {}
        if data.get("stat") == "OK":
            return candidate
        cursor -= timedelta(days=1)

    raise RuntimeError(f"Cannot find TWSE market data within 10 days before {report_date}")


def extract_report_date_from_text(text: str | None) -> str | None:
    if not text:
        return None

    source = str(text)
    match = re.search(r"\b(20\d{2})[./-](\d{1,2})[./-](\d{1,2})\b", source)
    if match:
        return normalize_date("-".join(match.groups()))

    zh_match = re.search(r"\b(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?\b", source)
    if zh_match:
        return normalize_date("-".join(zh_match.groups()))

    return None


def load_market_index() -> dict:
    data = fetch_json(twse_mi_index_url(MARKET_RESULT_DATE))
    tables = data["tables"]

    price_index = next(t for t in tables if t.get("title", "").startswith("115年06月11日 價格指數"))
    weighted = next(row for row in price_index["data"] if row[0] == "發行量加權股價指數")
    semiconductor = next(row for row in price_index["data"] if row[0] == "半導體類指數")
    electronics = next(row for row in price_index["data"] if row[0] == "電子工業類指數")
    finance = next(row for row in price_index["data"] if row[0] == "金融保險類指數")
    shipping = next(row for row in price_index["data"] if row[0] == "航運類指數")

    return {
        "weighted": {
            "close": weighted[1],
            "change": weighted[3],
            "pct": weighted[4],
        },
        "sectors": [
            {"name": "半導體", "pct": semiconductor[4]},
            {"name": "電子", "pct": electronics[4]},
            {"name": "金融", "pct": finance[4]},
            {"name": "航運", "pct": shipping[4]},
        ],
    }


def load_t86() -> dict:
    url = (
        "https://www.twse.com.tw/rwd/zh/fund/T86"
        f"?date={MARKET_RESULT_DATE.replace('-', '')}&selectType=ALLBUT0999&response=json"
    )
    data = fetch_json(url)
    if data.get("stat") != "OK" or "fields" not in data or "data" not in data:
        raise RuntimeError(f"TWSE T86 unavailable for {MARKET_RESULT_DATE}: {data.get('stat', 'missing fields')}")
    fields = data["fields"]
    rows = [dict(zip(fields, row)) for row in data["data"]]

    def top(column: str, reverse: bool) -> list[dict]:
        sorted_rows = sorted(rows, key=lambda row: to_int(row.get(column, "0")), reverse=reverse)
        result = []
        for row in sorted_rows[:10]:
            result.append(
                {
                    "code": row.get("證券代號", "").strip(),
                    "name": row.get("證券名稱", "").strip(),
                    "shares": to_int(row.get(column, "0")),
                }
            )
        return result

    columns = {
        "foreign": "外陸資買賣超股數(不含外資自營商)",
        "trust": "投信買賣超股數",
        "dealer": "自營商買賣超股數",
        "total": "三大法人買賣超股數",
    }

    return {
        key: {"buy": top(column, True), "sell": top(column, False)}
        for key, column in columns.items()
    }


def parse_etf_page(code: str) -> dict:
    html = fetch_text(f"https://www.etfinfo.tw/etf/{code}/holdings")

    title_match = re.search(r"<h1[^>]*>([^<]+)</h1>.*?<p class=\"muted subtitle\"[^>]*>([^<]+)</p>", html)
    price_match = re.search(
        r'<span class="price-value"[^>]*>([^<]+)</span><span class="price-unit"[^>]*>TWD</span>.*?<div class="price-up change-row"[^>]*><span[^>]*>▲ ([^<]+)</span><span[^>]*>\(([^)]+)\)</span>',
        html,
        re.S,
    )
    quick_match = re.search(
        r"快照 ([0-9-]+).*?前 10 大持股合計 ([0-9.]+)%，([^<]+)</p>.*?最大持股</span><strong[^>]*>([^<]+)</strong><small[^>]*>([^<]+)</small>",
        html,
        re.S,
    )
    freshness_match = re.search(r"最新持股異動</h2><p class=\"muted\"[^>]*>([^<]+)</p>", html)

    holdings = re.findall(
        r'<tr class="holding-row".*?<a href="/stock/([^"]+)" class="stock-code-link"[^>]*><!--\[-->([^<]+)<!--\]--></a><span class="stock-name-sub"[^>]*>([^<]+)</span>.*?<strong[^>]*>([0-9.]+%)</strong></td><td class="cell-number hide-mobile"[^>]*>([0-9,]+)</td>',
        html,
        re.S,
    )

    top_holdings = []
    for item in holdings[:10]:
        top_holdings.append(
            {
                "code": item[1].strip(),
                "name": item[2].strip(),
                "weight": item[3].strip(),
                "shares": item[4].strip(),
            }
        )

    return {
        "code": code,
        "name": title_match.group(1).strip(),
        "subtitle": title_match.group(2).strip(),
        "price": price_match.group(1).strip(),
        "change": price_match.group(2).strip(),
        "pct": price_match.group(3).strip(),
        "snapshot": quick_match.group(1).strip(),
        "top10_concentration": quick_match.group(2).strip(),
        "concentration_label": quick_match.group(3).strip(),
        "largest_holding": quick_match.group(4).strip(),
        "largest_weight": quick_match.group(5).strip(),
        "freshness": freshness_match.group(1).strip(),
        "top_holdings": top_holdings,
    }


GLOBAL_MARKET = {
    "date": "2026-06-11",
    "summary": "美股在中東風險暫時降溫後強彈，晶片股帶頭回升，對台股今晨情緒偏正面，但反彈後追價風險同步升高。",
    "items": [
        "S&P 500 上漲 1.8% 至 7,394.30。",
        "Nasdaq 上漲 2.5% 至 25,809.66。",
        "Dow Jones 上漲 1.9% 至 50,848.75。",
        "晶片股明顯反彈，油價回落，有利台股 AI 與半導體情緒修復。",
    ],
    "source_label": "AP, 2026-06-11 U.S. market close roundup",
    "source_url": "https://apnews.com/article/f89a3d0e7e096199f393cf2d55da5e0e",
}


def format_shares(value: int) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}{abs(value):,}"


def render_rank_table(title: str, buy_rows: list[dict], sell_rows: list[dict]) -> str:
    rows = []
    for idx in range(10):
        buy = buy_rows[idx]
        sell = sell_rows[idx]
        rows.append(
            f"""
            <tr>
              <td>{idx + 1}</td>
              <td>{buy['name']} {buy['code']}</td>
              <td class="pos">{format_shares(buy['shares'])}</td>
              <td>{sell['name']} {sell['code']}</td>
              <td class="neg">{format_shares(sell['shares'])}</td>
            </tr>
            """
        )
    return f"""
    <section class="card">
      <h3>{title}</h3>
      <div class="table-wrap">
        <table>
          <thead>
            <tr><th>名次</th><th>買超</th><th>股數</th><th>賣超</th><th>股數</th></tr>
          </thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
    </section>
    """


def render_etf_block(etf: dict) -> str:
    holding_rows = "".join(
        f"<tr><td>{row['code']}</td><td>{row['name']}</td><td>{row['weight']}</td><td>{row['shares']}</td></tr>"
        for row in etf["top_holdings"][:10]
    )
    return f"""
    <section class="card">
      <div class="split">
        <div>
          <h3>{etf['code']} {etf['name']}</h3>
          <p>{etf['subtitle']}</p>
          <ul class="bullets">
            <li>收盤 {etf['price']} 元，單日上漲 {etf['change']} 元（{etf['pct']}）。</li>
            <li>最新快照 {etf['snapshot']}，前十大集中度 {etf['top10_concentration']}%，屬於 {etf['concentration_label']}。</li>
            <li>最大持股 {etf['largest_holding']}，權重 {etf['largest_weight']}。</li>
            <li>{etf['freshness']}</li>
          </ul>
        </div>
        <div class="mini">
          <div class="metric"><span>ETF 價格</span><strong>{etf['price']}</strong></div>
          <div class="metric"><span>單日漲幅</span><strong class="pos">{etf['pct']}</strong></div>
          <div class="metric"><span>前十集中</span><strong>{etf['top10_concentration']}%</strong></div>
          <div class="metric"><span>最大持股</span><strong>{etf['largest_holding']}</strong></div>
        </div>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>代號</th><th>名稱</th><th>權重</th><th>股數</th></tr></thead>
          <tbody>{holding_rows}</tbody>
        </table>
      </div>
    </section>
    """


def render_html(market: dict, chips: dict, etf_a: dict, etf_b: dict) -> str:
    foreign_sell_top = chips["foreign"]["sell"][:3]
    trust_buy_top = chips["trust"]["buy"][:3]
    total_sell_top = chips["total"]["sell"][:3]

    headline = (
        f"台股 {MARKET_RESULT_DATE} 收在 {market['weighted']['close']}，"
        f"下跌 {market['weighted']['change']} 點（{market['weighted']['pct']}%）；"
        "美股隔夜強彈有助今晨情緒修復，但 00403A 與 00981A 仍見明顯法人調節，操作上宜偏分批。"
    )

    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>台股晨報 {REPORT_DATE}</title>
  <style>
    :root {{
      --bg: #f4f1ea;
      --paper: #fffdf8;
      --ink: #1f2937;
      --muted: #6b7280;
      --line: #dfd6c8;
      --brand: #0f3d3e;
      --accent: #b85c38;
      --up: #0f9d58;
      --down: #c0392b;
      --warn: #b9770e;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Noto Sans TC", "Microsoft JhengHei", sans-serif;
      background:
        radial-gradient(circle at top right, rgba(184,92,56,.18), transparent 25%),
        linear-gradient(180deg, #f6f0e7 0%, var(--bg) 100%);
      color: var(--ink);
      line-height: 1.7;
    }}
    .page {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 24px 16px 48px;
    }}
    .hero {{
      background: linear-gradient(135deg, #132a2b 0%, #0f3d3e 55%, #24575a 100%);
      color: white;
      border-radius: 24px;
      padding: 28px 24px;
      box-shadow: 0 16px 40px rgba(15, 61, 62, 0.18);
    }}
    .eyebrow {{ font-size: 12px; letter-spacing: 0.14em; opacity: .78; text-transform: uppercase; }}
    h1 {{ margin: 8px 0 10px; font-size: 34px; line-height: 1.15; }}
    .hero p {{ margin: 0; max-width: 860px; color: rgba(255,255,255,.9); }}
    .hero-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-top: 18px;
    }}
    .hero-card, .metric, .card {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 18px;
    }}
    .hero-card {{
      padding: 14px 16px;
      color: var(--ink);
    }}
    .hero-card span, .metric span {{ display: block; font-size: 12px; color: var(--muted); }}
    .hero-card strong, .metric strong {{ display: block; margin-top: 4px; font-size: 22px; }}
    .section-title {{
      margin: 28px 0 12px;
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 22px;
    }}
    .section-title::before {{
      content: "";
      width: 14px;
      height: 14px;
      border-radius: 4px;
      background: var(--accent);
      display: inline-block;
    }}
    .grid {{
      display: grid;
      gap: 14px;
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }}
    .card {{ padding: 18px; }}
    .card h3 {{ margin: 0 0 10px; font-size: 18px; }}
    .bullets {{ margin: 0; padding-left: 18px; }}
    .split {{
      display: grid;
      gap: 16px;
      grid-template-columns: minmax(0, 1.6fr) minmax(260px, .8fr);
      align-items: start;
    }}
    .mini {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }}
    .metric {{ padding: 12px 14px; background: #faf6ef; }}
    .table-wrap {{ overflow-x: auto; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 640px;
      font-size: 14px;
    }}
    th, td {{
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }}
    th {{ color: var(--brand); background: #f7f0e5; }}
    .pos {{ color: var(--up); font-weight: 700; }}
    .neg {{ color: var(--down); font-weight: 700; }}
    .muted {{ color: var(--muted); }}
    .strategy td:first-child, .strategy th:first-child {{ white-space: nowrap; }}
    .footer {{
      margin-top: 24px;
      color: var(--muted);
      font-size: 13px;
    }}
    a {{ color: var(--accent); }}
    @media (max-width: 900px) {{
      .hero-grid, .grid, .split, .mini {{
        grid-template-columns: 1fr;
      }}
      h1 {{ font-size: 28px; }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <section class="hero">
      <div class="eyebrow">Taiwan Stock Morning Report</div>
      <h1>台股晨報 {REPORT_DATE}</h1>
      <p>{headline}</p>
      <div class="hero-grid">
        <div class="hero-card"><span>晨報日期</span><strong>{REPORT_DATE}</strong></div>
        <div class="hero-card"><span>台股基準日</span><strong>{MARKET_RESULT_DATE}</strong></div>
        <div class="hero-card"><span>加權指數</span><strong>{market['weighted']['close']}</strong></div>
        <div class="hero-card"><span>單日變動</span><strong class="neg">{market['weighted']['pct']}%</strong></div>
      </div>
    </section>

    <h2 class="section-title">市場指數與全球影響</h2>
    <div class="grid">
      <section class="card">
        <h3>台股指數重點</h3>
        <ul class="bullets">
          <li>加權指數收在 {market['weighted']['close']}，下跌 {market['weighted']['change']} 點，跌幅 {market['weighted']['pct']}%。</li>
          <li>半導體類指數 {market['sectors'][0]['pct']}%，電子類 {market['sectors'][1]['pct']}%，金融類 {market['sectors'][2]['pct']}%，航運類 {market['sectors'][3]['pct']}%。</li>
          <li>盤面呈現「權值整理、金融與航運撐盤」結構，表示資金並未全面撤出，只是高位轉倉。</li>
        </ul>
      </section>
      <section class="card">
        <h3>全球市場影響</h3>
        <p class="muted">基準：{GLOBAL_MARKET['date']}</p>
        <ul class="bullets">
          {''.join(f'<li>{item}</li>' for item in GLOBAL_MARKET['items'])}
        </ul>
        <p>{GLOBAL_MARKET['summary']}</p>
      </section>
    </div>

    <h2 class="section-title">三大法人 Top 10</h2>
    <div class="grid">
      {render_rank_table("外資買超 / 賣超前 10", chips["foreign"]["buy"], chips["foreign"]["sell"])}
      {render_rank_table("投信買超 / 賣超前 10", chips["trust"]["buy"], chips["trust"]["sell"])}
      {render_rank_table("自營商買超 / 賣超前 10", chips["dealer"]["buy"], chips["dealer"]["sell"])}
      {render_rank_table("三大法人合計買超 / 賣超前 10", chips["total"]["buy"], chips["total"]["sell"])}
    </div>

    <h2 class="section-title">00981A / 00403A 每日成分股報告</h2>
    {render_etf_block(etf_a)}
    {render_etf_block(etf_b)}

    <h2 class="section-title">ETF 配置建議</h2>
    <section class="card">
      <div class="table-wrap">
        <table class="strategy">
          <thead>
            <tr><th>風格</th><th>股票部位</th><th>00981A</th><th>00403A</th><th>觀察重點</th></tr>
          </thead>
          <tbody>
            <tr><td>保守型</td><td>40% 以下</td><td>先不追，等外資回補</td><td>暫不攤平</td><td>先看台積電與 0050 賣壓是否縮小。</td></tr>
            <tr><td>均衡型</td><td>50%-60%</td><td>只做分批回補</td><td>等待跌深後量縮止穩</td><td>美股晶片續強才有利主動式 ETF 修復。</td></tr>
            <tr><td>進取型</td><td>65%-75%</td><td>偏向優先觀察 00981A</td><td>00403A 僅小量試單</td><td>00981A 昨日雖被法人賣超，但外資仍小幅買超，結構較 00403A 中性。</td></tr>
          </tbody>
        </table>
      </div>
    </section>

    <h2 class="section-title">交易策略</h2>
    <div class="grid">
      <section class="card">
        <h3>今日偏多但不追高</h3>
        <ul class="bullets">
          <li>美股與晶片股回穩，台股今晨有望先開高或開平偏強，但前一日台股權值未止穩，容易出現開高震盪。</li>
          <li>外資賣超前段仍集中在 {foreign_sell_top[0]['name']}、{foreign_sell_top[1]['name']}、{foreign_sell_top[2]['name']} 等大型 ETF／權值部位，代表外資風險偏好還沒完全恢復。</li>
          <li>投信買超偏向 {trust_buy_top[0]['name']}、{trust_buy_top[1]['name']}、{trust_buy_top[2]['name']}，說明內資仍沿著電子與金融輪動布局。</li>
        </ul>
      </section>
      <section class="card">
        <h3>執行節奏</h3>
        <ul class="bullets">
          <li>早盤若台積電、聯發科、鴻海同步紅盤且量能不爆，才考慮分批承接成長股。</li>
          <li>00403A 因三大法人合計賣超壓力最大，今天只適合觀察，不適合追價。</li>
          <li>00981A 若盤中回測不破前低，可列為較優先的主動式 ETF 觀察標的。</li>
          <li>若盤中再度看到 {total_sell_top[0]['name']}、{total_sell_top[1]['name']}、{total_sell_top[2]['name']} 這類賣壓擴大，代表市場仍在防守。</li>
        </ul>
      </section>
    </div>

    <h2 class="section-title">風險提醒</h2>
    <section class="card">
      <ul class="bullets">
        <li>這份晨報日期是 {REPORT_DATE}，台股法人與指數基準日是 {MARKET_RESULT_DATE}；若開盤後國際消息突變，盤中解讀需即時修正。</li>
        <li>00981A 與 00403A 都高度連動台積電、聯電、PCB、AI 伺服器鏈，單一族群回檔會放大 ETF 波動。</li>
        <li>外資雖對 00981A 小幅買超 4,650,613 股，但自營商大幅調節，代表籌碼並未完全轉強。</li>
        <li>00403A 外資賣超 132,671,849 股、三大法人合計賣超 330,737,173 股，是本次晨報最明顯的防守訊號。</li>
      </ul>
    </section>

    <div class="footer">
      <p>完整公開版：<a href="{PUBLIC_URL}">{PUBLIC_URL}</a></p>
      <p>資料來源：TWSE MI_INDEX、TWSE T86、ETF資訊網成分股頁、{GLOBAL_MARKET['source_label']}。</p>
    </div>
  </div>
</body>
</html>
"""


def build_line_message(market: dict) -> str:
    return (
        f"台股晨報 {REPORT_DATE}\n\n"
        f"1. 台股基準日 {MARKET_RESULT_DATE} 加權指數收 {market['weighted']['close']}，"
        f"下跌 {market['weighted']['change']} 點（{market['weighted']['pct']}%）。\n"
        "2. 美股 6/11 強彈，S&P 500 +1.8%、Nasdaq +2.5%，晶片股回升，有利今晨情緒修復。\n"
        "3. 外資對 00981A 小幅買超，但 00403A 仍遭大幅調節，主動式 ETF 以分批觀察為主。\n"
        "4. 投信買盤仍偏電子與金融，今天策略是不追高、等權值量價確認後再加碼。\n"
        "5. 風險在於台積電若無法續強，反彈容易轉震盪。\n\n"
        f"完整報告：\n{PUBLIC_URL}"
    )


def write_outputs(html: str, line_text: str) -> None:
    index_path = ROOT / "index.html"
    archive_path = ROOT / "reports" / f"{REPORT_DATE}.html"
    index_path.write_text(html, encoding="utf-8")
    archive_path.write_text(html, encoding="utf-8")

    reports_index_path = ROOT / "reports" / "index.json"
    if reports_index_path.exists():
        reports_index = json.loads(reports_index_path.read_text(encoding="utf-8-sig"))
    else:
        reports_index = {"latest": REPORT_DATE, "reports": []}

    existing_dates = {item["date"] for item in reports_index.get("reports", [])}
    if REPORT_DATE not in existing_dates:
        reports_index.setdefault("reports", []).append(
            {
                "date": REPORT_DATE,
                "label": REPORT_DATE.replace("-", "/"),
                "marketResultDate": MARKET_RESULT_DATE,
            }
        )
    reports_index["latest"] = REPORT_DATE
    reports_index["reports"] = sorted(reports_index["reports"], key=lambda item: item["date"])
    reports_index_path.write_text(
        json.dumps(reports_index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    line_payload = {"messages": [{"type": "text", "text": line_text}]}
    out_dir = ROOT.parent / "taiwan-stock"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"line-message-{REPORT_DATE}.json").write_text(
        json.dumps(line_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Taiwan stock morning report.")
    parser.add_argument("--report-date", default=os.getenv("REPORT_DATE"), help="Report date in YYYY-MM-DD.")
    parser.add_argument("--market-result-date", default=None, help="TWSE market data date in YYYY-MM-DD.")
    parser.add_argument("--line-text", default=os.getenv("LINE_TEXT"), help="Raw LINE text containing the requested date.")
    args = parser.parse_args()

    global REPORT_DATE, MARKET_RESULT_DATE
    requested_date = args.report_date or extract_report_date_from_text(args.line_text)
    if not requested_date:
        raise SystemExit("Missing report date. Pass --report-date YYYY-MM-DD or --line-text containing a date.")

    REPORT_DATE = normalize_date(requested_date)
    MARKET_RESULT_DATE = resolve_market_result_date(REPORT_DATE, args.market_result_date)

    market = load_market_index()
    chips = load_t86()
    etf_a = parse_etf_page("00981A")
    etf_b = parse_etf_page("00403A")
    html = render_html(market, chips, etf_a, etf_b)
    line_text = build_line_message(market)
    write_outputs(html, line_text)
    print(json.dumps({"report_date": REPORT_DATE, "market_result_date": MARKET_RESULT_DATE}, ensure_ascii=False))


if __name__ == "__main__":
    main()
