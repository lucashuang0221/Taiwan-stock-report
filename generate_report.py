from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PUBLIC_URL = "https://taiwan-stock-report-16l.pages.dev/"
TWSE_MI_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
TWSE_T86_URL = "https://www.twse.com.tw/rwd/zh/fund/T86"

REPORT_DATE = ""
MARKET_RESULT_DATE = ""


def run_curl(url: str) -> str:
    result = subprocess.run(
        ["curl.exe", "-L", "-s", "-A", "Mozilla/5.0", url],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout


def fetch_json(url: str) -> dict:
    return json.loads(run_curl(url))


def normalize_date(value: str) -> str:
    value = value.strip()
    match = re.fullmatch(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})", value)
    if match:
        year, month, day = map(int, match.groups())
        return date(year, month, day).isoformat()
    return date.fromisoformat(value.replace("/", "-")).isoformat()


def extract_report_date_from_text(text: str | None) -> str | None:
    if not text:
        return None
    match = re.search(r"\b(20\d{2})[./-](\d{1,2})[./-](\d{1,2})\b", text)
    if match:
        return normalize_date("-".join(match.groups()))
    match = re.search(r"\b(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\b", text)
    if match:
        return normalize_date("-".join(match.groups()))
    return None


def taipei_today() -> date:
    return (datetime.utcnow() + timedelta(hours=8)).date()


def twse_mi_index_url(market_date: str) -> str:
    compact = market_date.replace("-", "")
    return f"{TWSE_MI_URL}?date={compact}&type=ALLBUT0999&response=json"


def twse_t86_url(market_date: str) -> str:
    compact = market_date.replace("-", "")
    return f"{TWSE_T86_URL}?date={compact}&selectType=ALLBUT0999&response=json"


def resolve_market_result_date(report_date: str, explicit_market_date: str | None) -> str:
    if explicit_market_date:
        return normalize_date(explicit_market_date)

    report_day = date.fromisoformat(report_date)
    start_day = report_day
    if report_day >= taipei_today():
        start_day = report_day - timedelta(days=1)

    cursor = start_day
    for _ in range(14):
        candidate = cursor.isoformat()
        try:
            data = fetch_json(twse_mi_index_url(candidate))
        except Exception:
            data = {}
        if data.get("stat") == "OK":
            return candidate
        cursor -= timedelta(days=1)

    raise RuntimeError(f"無法為 {report_date} 找到可用的 TWSE 交易資料日")


def to_int(value: str | int | float | None) -> int:
    return int(str(value or "0").replace(",", "").strip() or "0")


def to_float(value: str | int | float | None) -> float:
    return float(str(value or "0").replace(",", "").replace("%", "").strip() or "0")


def fmt_int(value: int) -> str:
    return f"{value:,}"


def fmt_signed_int(value: int) -> str:
    return f"{value:+,}"


def fmt_float(value: float) -> str:
    return f"{value:,.2f}"


def pct_class(value: str | float) -> str:
    number = to_float(value)
    if number > 0:
        return "pos"
    if number < 0:
        return "neg"
    return "neu"


def pct_word(value: str | float) -> str:
    number = to_float(value)
    if number > 0:
        return "上漲"
    if number < 0:
        return "下跌"
    return "持平"


def pct_sign(value: str | float) -> str:
    number = to_float(value)
    if number > 0:
        return "+"
    if number < 0:
        return "-"
    return ""


def clean_change_sign(raw: str) -> str:
    if "green" in raw:
        return "-"
    if "red" in raw:
        return "+"
    return ""


def load_market_index() -> dict:
    data = fetch_json(twse_mi_index_url(MARKET_RESULT_DATE))
    if data.get("stat") != "OK":
        raise RuntimeError(f"TWSE MI_INDEX 讀取失敗：{MARKET_RESULT_DATE}")

    table0 = data["tables"][0]["data"]
    weighted = table0[1]
    tw50 = table0[3]
    sectors = data["tables"][1]["data"]
    quotes = data["tables"][8]["data"]

    quote_map = {}
    for row in quotes:
        if len(row) < 11:
            continue
        code = row[0].strip()
        quote_map[code] = {
            "code": code,
            "name": row[1].strip(),
            "volume": to_int(row[2]),
            "value": to_int(row[4]),
            "open": row[5].strip(),
            "high": row[6].strip(),
            "low": row[7].strip(),
            "close": row[8].strip(),
            "change": clean_change_sign(row[9]) + row[10].strip(),
        }

    return {
        "weighted": {
            "name": weighted[0].strip(),
            "close": weighted[1].strip(),
            "change": clean_change_sign(weighted[2]) + weighted[3].strip(),
            "pct": weighted[4].strip(),
        },
        "tw50": {
            "close": tw50[1].strip(),
            "pct": tw50[4].strip(),
        },
        "sectors": [
            {
                "name": row[0].strip(),
                "close": row[1].strip(),
                "change": clean_change_sign(row[2]) + row[3].strip(),
                "pct": row[4].strip(),
            }
            for row in sectors
        ],
        "quotes": quote_map,
    }


def load_t86() -> dict:
    data = fetch_json(twse_t86_url(MARKET_RESULT_DATE))
    if data.get("stat") != "OK":
        raise RuntimeError(f"TWSE T86 讀取失敗：{MARKET_RESULT_DATE}")

    rows = []
    for raw in data["data"]:
        if len(raw) < 19:
            continue
        rows.append(
            {
                "code": raw[0].strip(),
                "name": raw[1].strip(),
                "foreign": to_int(raw[4]),
                "trust": to_int(raw[10]),
                "dealer": to_int(raw[17]),
                "total": to_int(raw[18]),
            }
        )

    def rank(column: str, reverse: bool) -> list[dict]:
        return sorted(rows, key=lambda row: row[column], reverse=reverse)[:10]

    return {
        "rows": rows,
        "foreign": {"buy": rank("foreign", True), "sell": rank("foreign", False)},
        "trust": {"buy": rank("trust", True), "sell": rank("trust", False)},
        "dealer": {"buy": rank("dealer", True), "sell": rank("dealer", False)},
        "total": {"buy": rank("total", True), "sell": rank("total", False)},
    }


def parse_etf_page(code: str) -> dict:
    page = run_curl(f"https://www.etfinfo.tw/etf/{code}/holdings")

    title_match = re.search(r"<title>(.*?)</title>", page, re.S)
    title_text = html.unescape(title_match.group(1)).strip() if title_match else code

    h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S)
    h1_text = html.unescape(re.sub(r"<[^>]+>", "", h1_match.group(1))).strip() if h1_match else title_text

    subtitle_match = re.search(r'<p class="muted subtitle"[^>]*>(.*?)</p>', page, re.S)
    subtitle_text = html.unescape(re.sub(r"<[^>]+>", "", subtitle_match.group(1))).strip() if subtitle_match else ""

    price_match = re.search(r'<span class="price-value"[^>]*>(.*?)</span>', page, re.S)
    price = html.unescape(price_match.group(1)).strip() if price_match else "資料不足"

    change_match = re.search(
        r'<div class="price-(?:up|down) change-row"[^>]*><span[^>]*>(.*?)</span><span[^>]*>\((.*?)\)</span>',
        page,
        re.S,
    )
    change = html.unescape(change_match.group(1)).replace("＋", "+").replace("－", "-").strip() if change_match else "資料不足"
    pct = html.unescape(change_match.group(2)).strip() if change_match else "資料不足"

    updated_match = re.search(r"([0-9]{4}/[0-9]{2}/[0-9]{2}) 更新", html.unescape(page))
    updated = updated_match.group(1) if updated_match else "資料不足"

    meta = {}
    meta_match = re.search(
        rf'"{code}".*?"(20\d{{2}}-\d{{2}}-\d{{2}})",([0-9]+),([0-9]+),(-?[0-9.]+),(-?[0-9.]+),(-?[0-9.]+),(-?[0-9.]+)',
        page,
        re.S,
    )
    if meta_match:
        meta = {
            "data_date": meta_match.group(1),
            "aum": to_int(meta_match.group(2)),
            "beneficiaries": to_int(meta_match.group(3)),
            "daily_change": meta_match.group(4),
            "nav": meta_match.group(5),
            "premium": meta_match.group(6),
            "price_meta": meta_match.group(7),
        }

    holdings = []
    for row in re.findall(r'<tr class="holding-row".*?</tr>', page, re.S):
        row_text = html.unescape(re.sub(r"<[^>]+>", " ", row))
        row_text = re.sub(r"\s+", " ", row_text).strip()
        match = re.match(r"([0-9A-Z]+)\s+(.+?)\s+([0-9]+(?:\.[0-9]+)?)%", row_text)
        shares = re.findall(r"([0-9]{1,3}(?:,[0-9]{3})+)", row_text)
        if not match:
            continue
        holdings.append(
            {
                "code": match.group(1),
                "name": match.group(2).strip(),
                "weight": f"{match.group(3)}%",
                "shares": shares[0] if shares else "資料不足",
            }
        )

    return {
        "code": code,
        "name": h1_text,
        "subtitle": subtitle_text,
        "price": price if price != "資料不足" else meta.get("price_meta", "資料不足"),
        "change": change if change != "資料不足" else meta.get("daily_change", "資料不足"),
        "pct": pct,
        "updated": updated if updated != "資料不足" else meta.get("data_date", "資料不足"),
        "nav": meta.get("nav", "資料不足"),
        "premium": meta.get("premium", "資料不足"),
        "aum": meta.get("aum", 0),
        "beneficiaries": meta.get("beneficiaries", 0),
        "top_holdings": holdings[:10],
        "source": f"https://www.etfinfo.tw/etf/{code}/holdings",
    }


def stock_theme(code: str, name: str) -> str:
    mapping = {
        "2330": "晶圓代工 / AI 權值",
        "2303": "晶圓代工",
        "2317": "AI 伺服器 / 電子代工",
        "2327": "被動元件 / AI 零組件",
        "2383": "PCB / 高速材料",
        "2454": "IC 設計",
        "3017": "散熱",
        "3231": "AI 伺服器",
        "3661": "伺服器平台",
    }
    if code in mapping:
        return mapping[code]
    if any(keyword in name for keyword in ["電", "半導體", "光", "網"]):
        return "電子 / 科技"
    if "金" in name:
        return "金融"
    if any(keyword in name for keyword in ["航", "運"]):
        return "航運 / 運輸"
    if any(keyword in name for keyword in ["塑", "化"]):
        return "塑化"
    return "其他"


def strongest_sectors(market: dict) -> list[dict]:
    ranked = sorted(market["sectors"], key=lambda row: to_float(row["pct"]), reverse=True)[:5]
    reasons = {
        "食品": "資金避開電子權值後轉向防禦型內需。",
        "塑膠": "油價回落與低基期輪動支撐評價修復。",
        "航運": "短線資金偏向非電子題材與景氣循環股。",
        "貿易百貨": "內需題材相對抗震。",
        "油電燃氣": "防禦性與成本下降預期帶來資金回流。",
    }
    rows = []
    for sector in ranked:
        reason = next((text for key, text in reasons.items() if key in sector["name"]), "短線資金自大型電子股外溢，往相對低基期族群輪動。")
        rows.append(
            {
                "name": sector["name"],
                "pct": sector["pct"],
                "reason": reason,
                "flow": "若開盤後量能續強，代表輪動還沒結束；若量縮，容易只是一日反彈。",
            }
        )
    return rows


def recommendation_rows(chips: dict, quotes: dict) -> list[dict]:
    candidates = []
    for row in sorted(chips["rows"], key=lambda item: item["total"], reverse=True):
        if not row["code"].isdigit() or len(row["code"]) != 4 or row["code"].startswith("00"):
            continue
        quote = quotes.get(row["code"])
        if not quote:
            continue
        close = to_float(quote["close"])
        if close <= 0:
            continue
        candidates.append(
            {
                "stock": f"{row['name']} {row['code']}",
                "theme": stock_theme(row["code"], row["name"]),
                "logic": f"三大法人合計 {fmt_signed_int(row['total'])} 張，外資 {fmt_signed_int(row['foreign'])} 張，籌碼相對順勢。",
                "entry": f"{fmt_float(close * 0.985)} - {fmt_float(close * 1.01)}",
                "stop": fmt_float(close * 0.95),
                "target": f"{fmt_float(close * 1.05)} - {fmt_float(close * 1.10)}",
            }
        )
        if len(candidates) >= 6:
            break
    return candidates


def global_market_context() -> dict:
    if MARKET_RESULT_DATE == "2026-06-26":
        return {
            "date": "2026-06-26",
            "headline": "Reuters 6/26 指出，S&P 500 收黑、晶片股重挫，全球股市同步受科技賣壓拖累。",
            "items": [
                "Reuters 6/26 收盤報導：晶片與科技股是主要拖累來源，代表今天台股電子權值開盤仍要先看賣壓是否延續。",
                "Reuters 同日全球市場報導顯示，科技股回檔不只限於美股，資金風險偏好有降溫跡象。",
                "Google News 可驗證的 Reuters 條目顯示 6/26 市場主軸為 'chips tumble' 與 'tech selloff drags markets'，這對台股半導體與 AI 供應鏈偏負面。",
                "GuruFocus 的 VIX 月度資料顯示 2026 年 6 月讀數約 18.41，代表恐慌未失控，但風險偏好明顯不如前段高點。",
                "因此今天台股若出現開高，較合理的解讀是跌深技術反彈，而不是直接視為趨勢翻多。",
            ],
            "sources": [
                ("Reuters via Google News: S&P 500 ends lower; chips tumble and Moderna rallies", "https://news.google.com/rss/search?q=2026-06-26+Reuters+S%26P+500+ends+lower+chips+tumble&hl=en-US&gl=US&ceid=US:en"),
                ("Reuters via Google News: World stocks edge lower as tech selloff drags markets", "https://news.google.com/rss/search?q=2026-06-26+Reuters+world+stocks+edge+lower+tech+selloff&hl=en-US&gl=US&ceid=US:en"),
                ("GuruFocus: VIX 2026-06", "https://www.gurufocus.com/economic_indicators/1326/vix-cboe-volatility-index-average"),
            ],
        }

    return {
        "date": MARKET_RESULT_DATE,
        "headline": "國際市場區塊以新聞稿型來源為主，重點在科技股風險偏好與 VIX 變化。",
        "items": [
            "若沒有可靠的指數即時 API，優先用可驗證的新聞收盤敘事，不用未驗證點位硬湊數字。",
            "科技股與晶片股的強弱，仍是隔日台股電子權值與主動式 ETF 的主要方向盤。",
            "VIX 若維持 20 以下，多半代表市場仍有風險承受能力，但高估值股會先面臨估值收縮。",
        ],
        "sources": [
            ("Google News", "https://news.google.com/"),
        ],
    }


def render_institution_table(label: str, column: str, data: dict) -> str:
    rows = []
    for idx in range(min(10, len(data["buy"]), len(data["sell"]))):
        buy = data["buy"][idx]
        sell = data["sell"][idx]
        rows.append(
            f"""
            <tr>
              <td>{idx + 1}</td>
              <td>{buy['name']} <span>{buy['code']}</span></td>
              <td class="pos">{fmt_signed_int(buy[column])}</td>
              <td>{sell['name']} <span>{sell['code']}</span></td>
              <td class="neg">{fmt_signed_int(sell[column])}</td>
            </tr>
            """
        )
    return f"""
    <section class="card">
      <div class="card-head"><h3>{label}</h3><span>Top 10，單位：張</span></div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>序</th><th>買超</th><th>股數</th><th>賣超</th><th>股數</th></tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
    </section>
    """


def render_etf_holdings(etf: dict, quotes: dict) -> str:
    rows = []
    for holding in etf["top_holdings"]:
        quote = quotes.get(holding["code"], {})
        close = quote.get("close", "資料不足")
        change = quote.get("change", "資料不足")
        rows.append(
            f"""
            <tr>
              <td>{etf['code']}</td>
              <td>{holding['name']} {holding['code']}</td>
              <td>{holding['weight']}</td>
              <td>{stock_theme(holding['code'], holding['name'])}</td>
              <td>{close} / {change}</td>
              <td>{holding['shares']}</td>
              <td>權重越高，對 ETF 淨值與今日情緒的影響越大。</td>
            </tr>
            """
        )
    return "".join(rows)


def render_html(market: dict, chips: dict, etf_a: dict, etf_b: dict) -> str:
    weighted = market["weighted"]
    move_class = pct_class(weighted["pct"])
    support = fmt_float(to_float(weighted["close"]) * 0.985)
    resistance = fmt_float(to_float(weighted["close"]) * 1.015)
    foreign_buy = chips["foreign"]["buy"][0]
    foreign_sell = chips["foreign"]["sell"][0]
    sectors = strongest_sectors(market)
    recs = recommendation_rows(chips, market["quotes"])
    global_block = global_market_context()

    rec_rows = "".join(
        f"""
        <tr>
          <td>{row['stock']}</td>
          <td>{row['theme']}</td>
          <td>{row['logic']}</td>
          <td>{row['entry']}</td>
          <td>{row['stop']}</td>
          <td>{row['target']}</td>
        </tr>
        """
        for row in recs
    )

    sector_rows = "".join(
        f"""
        <tr>
          <td>{row['name']}</td>
          <td class="{pct_class(row['pct'])}">{pct_sign(row['pct'])}{row['pct']}%</td>
          <td>{row['reason']}</td>
          <td>{row['flow']}</td>
        </tr>
        """
        for row in sectors
    )

    source_links = "".join(f'<li><a href="{url}">{label}</a></li>' for label, url in global_block["sources"])

    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
  <title>台股晨間投資報告 {REPORT_DATE}</title>
  <style>
    :root {{
      --navy:#0f172a;
      --blue:#38bdf8;
      --bg:#f8fafc;
      --line:#cbd5e1;
      --green:#10b981;
      --orange:#f59e0b;
      --red:#ef4444;
      --ink:#111827;
      --muted:#64748b;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--ink); font-family:"Noto Sans TC","Microsoft JhengHei",Arial,sans-serif; line-height:1.65; }}
    .page {{ max-width:1180px; margin:0 auto; padding:20px 14px 48px; }}
    .hero {{ background:linear-gradient(135deg,#0f172a,#123052 58%,#0e7490); color:#fff; border-radius:8px; padding:24px; }}
    .badge {{ display:inline-flex; padding:5px 10px; border:1px solid rgba(255,255,255,.35); border-radius:999px; font-size:12px; color:#dbeafe; }}
    h1 {{ margin:12px 0 8px; font-size:32px; line-height:1.2; }}
    h2 {{ margin:28px 0 12px; font-size:22px; color:var(--navy); }}
    h3 {{ margin:0; font-size:17px; color:var(--navy); }}
    .hero p {{ margin:0; color:#e0f2fe; max-width:920px; }}
    .kpis {{ display:grid; grid-template-columns:repeat(6,minmax(0,1fr)); gap:10px; margin-top:18px; }}
    .kpi {{ background:rgba(255,255,255,.1); border:1px solid rgba(255,255,255,.18); border-radius:8px; padding:12px; min-height:86px; }}
    .kpi span,.card-head span,.muted {{ color:var(--muted); font-size:12px; }}
    .kpi span {{ color:#bae6fd; }}
    .kpi strong {{ display:block; margin-top:4px; font-size:21px; color:#fff; }}
    .read-order {{ display:grid; grid-template-columns:repeat(3,1fr); gap:12px; background:#111827; border-radius:8px; padding:14px; margin-top:14px; color:#e5e7eb; }}
    .grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; }}
    .card {{ background:#fff; border:1px solid var(--line); border-radius:8px; padding:16px; margin-bottom:14px; }}
    .card-head {{ display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:10px; }}
    .alert {{ border-left:4px solid var(--blue); background:#f8fafc; padding:12px; border-radius:6px; margin:10px 0; }}
    .alert.warn {{ border-left-color:var(--orange); }}
    .alert.risk {{ border-left-color:var(--red); }}
    .alert.good {{ border-left-color:var(--green); }}
    ul {{ margin:0; padding-left:20px; }}
    .table-wrap {{ overflow-x:auto; }}
    table {{ width:100%; border-collapse:collapse; min-width:760px; font-size:14px; }}
    th {{ background:var(--navy); color:#fff; text-align:left; padding:10px 12px; }}
    td {{ border-bottom:1px solid var(--line); padding:10px 12px; vertical-align:top; }}
    tbody tr:nth-child(even) {{ background:#f8fafc; }}
    td span {{ color:var(--muted); font-size:12px; }}
    .pos {{ color:var(--green); font-weight:700; }}
    .neg {{ color:var(--red); font-weight:700; }}
    .neu {{ color:var(--muted); font-weight:700; }}
    .footer {{ margin-top:22px; color:var(--muted); font-size:13px; }}
    a {{ color:#0369a1; }}
    @media (max-width:900px) {{
      .kpis,.grid,.read-order {{ grid-template-columns:1fr 1fr; }}
      h1 {{ font-size:27px; }}
    }}
    @media (max-width:640px) {{
      .kpis,.grid,.read-order {{ grid-template-columns:1fr; }}
      .hero {{ padding:18px; }}
      table {{ min-width:720px; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      <span class="badge">台股晨報自動化產出</span>
      <h1>台股晨間投資報告 {REPORT_DATE}</h1>
      <p>報告日為 {REPORT_DATE}；台股採用最新已完成交易資料 {MARKET_RESULT_DATE}。今日為盤前晨報，重點在判斷籌碼、國際情緒與 ETF 配置風險，不直接把盤前反應視為趨勢反轉。</p>
      <div class="kpis">
        <div class="kpi"><span>加權指數</span><strong>{weighted['close']}</strong></div>
        <div class="kpi"><span>日變動</span><strong class="{move_class}">{weighted['change']} / {weighted['pct']}%</strong></div>
        <div class="kpi"><span>台灣 50</span><strong>{market['tw50']['pct']}%</strong></div>
        <div class="kpi"><span>外資買超首位</span><strong>{foreign_buy['name']}</strong></div>
        <div class="kpi"><span>外資賣超首位</span><strong>{foreign_sell['name']}</strong></div>
        <div class="kpi"><span>盤勢情緒</span><strong>{'震盪偏空' if to_float(weighted['pct']) < 0 else '偏多但需確認量價'}</strong></div>
      </div>
    </section>

    <section class="read-order">
      <div><strong>1. 先看大盤</strong><br>確認加權指數是否只是跌深反彈，支撐壓力先抓 {support} / {resistance}。</div>
      <div><strong>2. 再看籌碼</strong><br>法人買賣超與 ETF 申贖方向，決定今天哪些股可以追、哪些只能等。</div>
      <div><strong>3. 最後看 ETF</strong><br>00981A、00403A 都高度連動台積電與 AI 供應鏈，不宜忽略集中度風險。</div>
    </section>

    <h2>1. 今日市場結論</h2>
    <section class="card">
      <ul>
        <li>加權指數 {pct_word(weighted['pct'])} {weighted['pct']}%，代表前一交易日權值股賣壓明顯，今天開盤先以修復盤或延續弱勢盤看待。</li>
        <li>外資買超首位為 {foreign_buy['name']}，外資賣超首位為 {foreign_sell['name']}，顯示資金沒有全面回流科技權值。</li>
        <li>00981A 與 00403A 都屬於高集中度主動式 ETF，若台積電與 AI 供應鏈沒有止穩，ETF 淨值波動會被放大。</li>
        <li>今天盤前支撐先看 {support}，壓力先看 {resistance}。若開高無量，不追；若量縮跌破支撐，先降槓桿與持股比重。</li>
        <li>操作優先順序是「先求風險可控，再求報酬」，不把單一利多新聞直接當成全市場翻多訊號。</li>
      </ul>
    </section>

    <h2>2. 法人買賣超前 10 名</h2>
    <div class="grid">
      {render_institution_table("外資買賣超", "foreign", chips["foreign"])}
      {render_institution_table("投信買賣超", "trust", chips["trust"])}
      {render_institution_table("自營商買賣超", "dealer", chips["dealer"])}
      {render_institution_table("三大法人合計", "total", chips["total"])}
    </div>

    <h2>3. 大盤與國際市場影響</h2>
    <div class="grid">
      <section class="card">
        <div class="card-head"><h3>台股大盤</h3><span>TWSE {MARKET_RESULT_DATE}</span></div>
        <ul>
          <li>加權指數收 {weighted['close']}，{pct_word(weighted['pct'])} {weighted['change']} 點，漲跌幅 {weighted['pct']}%。</li>
          <li>台灣 50 指數漲跌幅 {market['tw50']['pct']}%，代表大型權值股仍是盤勢主導核心。</li>
          <li>若今天台積電、聯發科、鴻海無法同步止穩，盤面再強也容易只剩局部題材股表現。</li>
          <li>期貨與台幣方向需在開盤後續看，但在現貨大跌之後，先假設市場容錯率下降。</li>
        </ul>
      </section>
      <section class="card">
        <div class="card-head"><h3>國際市場直接影響</h3><span>{global_block['date']}</span></div>
        <div class="alert good">{global_block['headline']}</div>
        <ul>{"".join(f"<li>{item}</li>" for item in global_block["items"])}</ul>
      </section>
    </div>

    <h2>4. 強勢族群</h2>
    <section class="card">
      <div class="table-wrap">
        <table>
          <thead><tr><th>族群</th><th>漲跌幅</th><th>強勢原因</th><th>續航判讀</th></tr></thead>
          <tbody>{sector_rows}</tbody>
        </table>
      </div>
    </section>

    <h2>5. ETF 00981A / 00403A 每日成分股報告</h2>
    <section class="card">
      <div class="card-head"><h3>{etf_a['code']} {etf_a['name']}</h3><span>資料更新 {etf_a['updated']}</span></div>
      <div class="alert warn">市價 {etf_a['price']}，漲跌 {etf_a['change']}（{etf_a['pct']}），NAV {etf_a['nav']}，折溢價 {etf_a['premium']}%。前十大權重合計約 {fmt_float(sum(to_float(row['weight']) for row in etf_a['top_holdings']))}% 。</div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>ETF</th><th>成分股</th><th>權重</th><th>族群</th><th>前一交易日表現</th><th>持股股數</th><th>解讀</th></tr></thead>
          <tbody>{render_etf_holdings(etf_a, market['quotes'])}</tbody>
        </table>
      </div>
    </section>
    <section class="card">
      <div class="card-head"><h3>{etf_b['code']} {etf_b['name']}</h3><span>資料更新 {etf_b['updated']}</span></div>
      <div class="alert warn">市價 {etf_b['price']}，漲跌 {etf_b['change']}（{etf_b['pct']}），NAV {etf_b['nav']}，折溢價 {etf_b['premium']}%。前十大權重合計約 {fmt_float(sum(to_float(row['weight']) for row in etf_b['top_holdings']))}% 。</div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>ETF</th><th>成分股</th><th>權重</th><th>族群</th><th>前一交易日表現</th><th>持股股數</th><th>解讀</th></tr></thead>
          <tbody>{render_etf_holdings(etf_b, market['quotes'])}</tbody>
        </table>
      </div>
    </section>

    <h2>6. ETF 配置與操作策略</h2>
    <div class="grid">
      <section class="card">
        <div class="table-wrap">
          <table>
            <thead><tr><th>類型</th><th>配置建議</th><th>操作重點</th></tr></thead>
            <tbody>
              <tr><td>保守型</td><td>股票 / ETF 合計 40% - 50%</td><td>先等支撐確認，不追開盤反彈。</td></tr>
              <tr><td>穩健型</td><td>股票 / ETF 合計 55% - 65%</td><td>00981A、00403A 可分批，搭配高流動性權值股。</td></tr>
              <tr><td>積極型</td><td>股票 / ETF 合計 65% - 75%</td><td>只追法人續買且開盤後放量延續的標的。</td></tr>
            </tbody>
          </table>
        </div>
      </section>
      <section class="card">
        <ul>
          <li>00981A 比較偏成長與 AI，適合在科技股止穩後分批切入，不適合在科技補跌日抄底重壓。</li>
          <li>00403A 台積電權重更高，若想押權值反彈可以看它，但也更容易受台積電影響。</li>
          <li>若今天盤中出現開高走低，ETF 部位不加碼；若尾盤站回開盤價且量能放大，再談追價。</li>
        </ul>
      </section>
    </div>

    <h2>7. 交易策略參考</h2>
    <section class="card">
      <div class="table-wrap">
        <table>
          <thead><tr><th>標的</th><th>主題</th><th>邏輯</th><th>進場區間</th><th>停損</th><th>目標</th></tr></thead>
          <tbody>{rec_rows}</tbody>
        </table>
      </div>
    </section>

    <h2>8. 風險提醒</h2>
    <section class="card">
      <div class="alert risk">今天最大的風險不是沒有機會，而是把跌深反彈誤判成新一輪趨勢多頭。若電子權值無法止穩，短線拉高都可能只是降低套牢成本的賣點。</div>
      <ul>
        <li>若美股科技股跌勢延續，台股開盤後最容易先反映在半導體、AI 伺服器、散熱與高速材料。</li>
        <li>主動式 ETF 的集中度高，當權值股同步回檔時，00981A 與 00403A 的淨值波動會高於廣泛型 ETF。</li>
        <li>請把停損與資金控管擺在選股前面，盤前報告只能提供框架，不能取代盤中量價確認。</li>
      </ul>
    </section>

    <footer class="footer">
      <p>固定公開網址：<a href="{PUBLIC_URL}">{PUBLIC_URL}</a></p>
      <p>資料來源：TWSE MI_INDEX、TWSE T86、ETF 資訊網 00981A / 00403A 成分股頁；國際市場參考如下：</p>
      <ul>{source_links}</ul>
      <p>本內容為研究與決策支援，不保證投資報酬，正式進出仍需搭配盤中量價與風險控管。</p>
    </footer>
  </main>
</body>
</html>
"""


def build_line_message(market: dict, chips: dict, etf_a: dict, etf_b: dict) -> str:
    weighted = market["weighted"]
    global_block = global_market_context()
    etf_a_concentration = fmt_float(sum(to_float(row["weight"]) for row in etf_a["top_holdings"]))
    etf_b_concentration = fmt_float(sum(to_float(row["weight"]) for row in etf_b["top_holdings"]))

    return (
        f"台股晨報 {REPORT_DATE}\n"
        f"採用最新交易資料：{MARKET_RESULT_DATE}\n\n"
        f"1. 加權指數 {weighted['close']}，{pct_word(weighted['pct'])} {weighted['change']} 點（{weighted['pct']}%），盤前先以修復或延續弱勢看待。\n"
        f"2. 國際面：{global_block['headline']}\n"
        f"3. 外資買超焦點：{chips['foreign']['buy'][0]['name']}；外資賣超焦點：{chips['foreign']['sell'][0]['name']}。\n"
        f"4. 00981A 市價 {etf_a['price']}、前十大集中度約 {etf_a_concentration}%；00403A 市價 {etf_b['price']}、前十大集中度約 {etf_b_concentration}%。\n"
        "5. 策略：不追開高，先看台積電與 AI 權值能否止穩；ETF 採分批，不把跌深反彈直接當翻多。\n\n"
        f"完整報告：{PUBLIC_URL}\n"
        "提醒：本內容為研究與決策支援，不保證投資報酬。"
    )


def write_outputs(report_html: str, line_text: str) -> None:
    reports_dir = ROOT / "reports"
    reports_dir.mkdir(exist_ok=True)

    (ROOT / "index.html").write_text(report_html, encoding="utf-8")
    (reports_dir / f"{REPORT_DATE}.html").write_text(report_html, encoding="utf-8")

    index_path = reports_dir / "index.json"
    if index_path.exists():
        reports_index = json.loads(index_path.read_text(encoding="utf-8-sig"))
    else:
        reports_index = {"latest": REPORT_DATE, "reports": []}

    reports = [item for item in reports_index.get("reports", []) if item.get("date") != REPORT_DATE]
    reports.append(
        {
            "date": REPORT_DATE,
            "label": REPORT_DATE.replace("-", "/"),
            "marketResultDate": MARKET_RESULT_DATE,
        }
    )
    reports_index["latest"] = REPORT_DATE
    reports_index["reports"] = sorted(reports, key=lambda item: item["date"])
    index_path.write_text(json.dumps(reports_index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    payload_dir = ROOT.parent / "taiwan-stock"
    payload_dir.mkdir(parents=True, exist_ok=True)
    payload = {"messages": [{"type": "text", "text": line_text}]}
    (payload_dir / f"line-message-{REPORT_DATE}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Lucas's Taiwan stock morning report.")
    parser.add_argument("--report-date", default=os.getenv("REPORT_DATE"))
    parser.add_argument("--market-result-date", default=None)
    parser.add_argument("--line-text", default=os.getenv("LINE_TEXT"))
    args = parser.parse_args()

    requested_date = args.report_date or extract_report_date_from_text(args.line_text)
    if not requested_date:
        raise SystemExit("Missing report date. Pass --report-date YYYY-MM-DD or --line-text containing a date.")

    global REPORT_DATE, MARKET_RESULT_DATE
    REPORT_DATE = normalize_date(requested_date)
    MARKET_RESULT_DATE = resolve_market_result_date(REPORT_DATE, args.market_result_date)

    market = load_market_index()
    chips = load_t86()
    etf_a = parse_etf_page("00981A")
    etf_b = parse_etf_page("00403A")

    report_html = render_html(market, chips, etf_a, etf_b)
    line_text = build_line_message(market, chips, etf_a, etf_b)
    write_outputs(report_html, line_text)

    print(json.dumps({"report_date": REPORT_DATE, "market_result_date": MARKET_RESULT_DATE}, ensure_ascii=False))


if __name__ == "__main__":
    main()
