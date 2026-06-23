from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PUBLIC_URL = "https://taiwan-stock-report-16l.pages.dev/"
TWSE_MI_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
TWSE_T86_URL = "https://www.twse.com.tw/rwd/zh/fund/T86"
REPORT_DATE = ""
MARKET_RESULT_DATE = ""


GLOBAL_MARKET = {
    "date": "2026-06-22",
    "headline": "美股 6/22 漲跌互見：Nasdaq -1.32%、S&P 500 -0.37%，但費半 +2.04%續創高；對台股是「權值半導體偏正向、科技大型股情緒偏分歧」的組合。",
    "items": [
        "美股四大指數：S&P 500 收 7,472.79（-0.37%）、Nasdaq 收 26,166.60（-1.32%）、Dow 收 51,712.71（+0.29%）、Russell 2000 收 3,004.40（+0.8%）。",
        "費半指數：SOX 收 14,634.72（+2.04%）並再創新高，直接支撐台股半導體、AI 伺服器、PCB、散熱與高階零組件。",
        "美債殖利率：10 年期約 4.49%-4.51%，短端殖利率升至高檔，代表 Fed 偏鷹預期仍壓抑高本益比科技股估值。",
        "原油與黃金：美伊談判降溫使油價回落，WTI 約 73.86 美元、Brent 約 77.52 美元；油價回落有助通膨預期，但債券殖利率未同步下降。",
        "VIX：6/22 收 17.28，較前一交易日上升，顯示市場對科技股與利率變數仍有避險需求。",
        "AI 與大型科技：費半續強但 Alphabet、Amazon、Broadcom 等大型科技轉弱，台股今日應偏向篩選半導體強勢鏈，不宜把所有科技股視為同步轉強。",
        "Fed 政策：市場重新定價升息風險，若本週 PCE 或 Fed 官員談話偏鷹，AI 與高估值權值股容易出現獲利了結。",
    ],
    "sources": [
        ("AP 6/22 美股收盤", "https://apnews.com/article/15484e7e5b168601a3f2c0061eb3ffd1"),
        ("經濟日報 6/22 費半與科技股", "https://money.udn.com/money/story/123398/9582116"),
        ("Cboe VIX", "https://www.cboe.com/tradable-products/vix/"),
        ("MarketWatch / Treasury yields", "https://www.marketwatch.com/livecoverage/stock-market-today-dow-s-p-500-investors-us-iran-peace-talks-brent-crude-declines/card/2-year-treasury-yield-climbs-to-levels-not-seen-since-early-2025-RmqjsbC1HLyOJItaIJxe"),
    ],
}


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
    text = run_curl(url)
    return json.loads(text)


def normalize_date(value: str) -> str:
    match = re.fullmatch(r"\s*(20\d{2})[./-](\d{1,2})[./-](\d{1,2})\s*", value)
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
    zh_match = re.search(r"\b(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?\b", text)
    if zh_match:
        return normalize_date("-".join(zh_match.groups()))
    return None


def twse_mi_index_url(market_date: str) -> str:
    return f"{TWSE_MI_URL}?date={market_date.replace('-', '')}&type=ALLBUT0999&response=json"


def twse_t86_url(market_date: str) -> str:
    return f"{TWSE_T86_URL}?date={market_date.replace('-', '')}&selectType=ALLBUT0999&response=json"


def resolve_market_result_date(report_date: str, explicit_market_date: str | None) -> str:
    if explicit_market_date:
        return normalize_date(explicit_market_date)
    cursor = date.fromisoformat(report_date)
    for _ in range(12):
        candidate = cursor.isoformat()
        try:
            data = fetch_json(twse_mi_index_url(candidate))
        except Exception:
            data = {}
        if data.get("stat") == "OK":
            return candidate
        cursor -= timedelta(days=1)
    raise RuntimeError(f"找不到 {report_date} 前 12 天內的 TWSE 交易資料")


def to_int(value: str | int | float | None) -> int:
    return int(str(value or "0").replace(",", "").strip() or "0")


def to_float(value: str | int | float | None) -> float:
    return float(str(value or "0").replace(",", "").replace("%", "").strip() or "0")


def fmt_int(value: int) -> str:
    return f"{value:,}"


def fmt_signed_int(value: int) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}{abs(value):,}"


def fmt_float(value: float) -> str:
    return f"{value:,.2f}"


def pct_class(value: str | float) -> str:
    return "pos" if to_float(value) > 0 else "neg" if to_float(value) < 0 else "neu"


def pct_word(value: str | float) -> str:
    num = to_float(value)
    if num > 0:
        return "上漲"
    if num < 0:
        return "下跌"
    return "持平"


def clean_change_sign(raw: str) -> str:
    if "green" in raw:
        return "-"
    if "red" in raw:
        return "+"
    return ""


def load_market_index() -> dict:
    data = fetch_json(twse_mi_index_url(MARKET_RESULT_DATE))
    if data.get("stat") != "OK":
        raise RuntimeError(f"TWSE MI_INDEX 無資料：{MARKET_RESULT_DATE}")

    index_rows = data["tables"][0]["data"]
    weighted = index_rows[0]
    non_fin = index_rows[1]
    tw50 = index_rows[3]
    sector_rows = data["tables"][1]["data"]
    listed_quotes = data["tables"][8]["data"]

    quotes = {}
    for row in listed_quotes:
        if len(row) >= 11:
            code = row[0].strip()
            change = clean_change_sign(row[9]) + row[10].strip()
            quotes[code] = {
                "code": code,
                "name": row[1].strip(),
                "volume": to_int(row[2]),
                "value": to_int(row[4]),
                "open": row[5],
                "high": row[6],
                "low": row[7],
                "close": row[8],
                "change": change,
            }

    return {
        "weighted": {
            "name": weighted[0],
            "close": weighted[1],
            "change": clean_change_sign(weighted[2]) + weighted[3],
            "pct": weighted[4],
        },
        "non_finance": {"close": non_fin[1], "pct": non_fin[4]},
        "tw50": {"close": tw50[1], "pct": tw50[4]},
        "sectors": [
            {"name": row[0], "close": row[1], "change": clean_change_sign(row[2]) + row[3], "pct": row[4]}
            for row in sector_rows[:8]
        ],
        "quotes": quotes,
    }


def load_t86() -> dict:
    data = fetch_json(twse_t86_url(MARKET_RESULT_DATE))
    if data.get("stat") != "OK":
        raise RuntimeError(f"TWSE T86 無資料：{MARKET_RESULT_DATE}")

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
        "foreign": {"buy": rank("foreign", True), "sell": rank("foreign", False)},
        "trust": {"buy": rank("trust", True), "sell": rank("trust", False)},
        "dealer": {"buy": rank("dealer", True), "sell": rank("dealer", False)},
        "total": {"buy": rank("total", True), "sell": rank("total", False)},
        "rows": rows,
    }


def parse_etf_page(code: str) -> dict:
    page = run_curl(f"https://www.etfinfo.tw/etf/{code}/holdings")
    title = re.search(r"<title>(.*?)</title>", page, re.S)
    title_text = html.unescape(title.group(1)).split(" 成分股")[0] if title else code
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S)
    subtitle = re.search(r'<p class="muted subtitle"[^>]*>(.*?)</p>', page, re.S)
    price = re.search(r'<span class="price-value"[^>]*>(.*?)</span>', page, re.S)
    change = re.search(r'<div class="price-(?:up|down) change-row"[^>]*><span[^>]*>(.*?)</span><span[^>]*>\((.*?)\)</span>', page, re.S)
    updated = re.search(r"成分股名單｜([0-9/]+) 更新", html.unescape(page))

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
        txt = html.unescape(re.sub(r"<[^>]+>", " ", row))
        txt = re.sub(r"\s+", " ", txt).strip()
        match = re.match(r"([0-9A-Z]+)\s+(.+?)\s+—", txt)
        weights = re.findall(r"([0-9]+(?:\.[0-9]+)?)%", txt)
        shares = re.findall(r"([0-9]{1,3}(?:,[0-9]{3})+)", txt)
        if match and weights:
            holdings.append(
                {
                    "code": match.group(1),
                    "name": match.group(2).strip(),
                    "weight": f"{weights[0]}%",
                    "shares": shares[0] if shares else "資料不足",
                }
            )

    return {
        "code": code,
        "name": html.unescape(re.sub(r"<[^>]+>", "", h1.group(1))).strip() if h1 else title_text,
        "subtitle": html.unescape(re.sub(r"<[^>]+>", "", subtitle.group(1))).strip() if subtitle else "",
        "price": html.unescape(price.group(1)).strip() if price else meta.get("price_meta", "資料不足"),
        "change": html.unescape(change.group(1)).replace("▲", "+").replace("▼", "-").strip() if change else meta.get("daily_change", "資料不足"),
        "pct": html.unescape(change.group(2)).strip() if change else "資料不足",
        "updated": updated.group(1) if updated else meta.get("data_date", "資料不足"),
        "nav": meta.get("nav", "資料不足"),
        "premium": meta.get("premium", "資料不足"),
        "aum": meta.get("aum", 0),
        "beneficiaries": meta.get("beneficiaries", 0),
        "top_holdings": holdings[:10],
        "source": f"https://www.etfinfo.tw/etf/{code}/holdings",
    }


def stock_theme(code: str, name: str) -> str:
    mapping = {
        "2330": "半導體 / AI 核心",
        "2303": "晶圓代工",
        "2317": "AI 伺服器 / 電子代工",
        "2327": "被動元件 / AI 電源",
        "2383": "PCB / 高速傳輸",
        "3661": "散熱 / AI 伺服器",
        "3017": "散熱",
        "3231": "伺服器",
        "2357": "品牌 / AI PC",
        "2454": "IC 設計",
    }
    if code in mapping:
        return mapping[code]
    if "電" in name or "光" in name:
        return "電子 / AI 供應鏈"
    if "金" in name or "銀" in name:
        return "金融"
    if "航" in name or "運" in name:
        return "航運"
    return "籌碼強勢股"


def common_stock_rows(chips: dict, quotes: dict, column: str) -> list[dict]:
    rows = []
    ranked = sorted(chips["rows"], key=lambda row: row[column], reverse=True)
    for row in ranked:
        if not (row["code"].isdigit() and len(row["code"]) == 4 and not row["code"].startswith("00")):
            continue
        quote = quotes.get(row["code"])
        if not quote:
            continue
        item = {**row, **quote, "theme": stock_theme(row["code"], row["name"])}
        rows.append(item)
        if len(rows) >= 8:
            break
    return rows


def recommendation_rows(chips: dict, quotes: dict) -> list[dict]:
    pool = common_stock_rows(chips, quotes, "total")
    if len(pool) < 6:
        pool.extend(common_stock_rows(chips, quotes, "foreign"))

    seen = set()
    result = []
    for row in pool:
        if row["code"] in seen:
            continue
        seen.add(row["code"])
        close = to_float(row["close"])
        if close <= 0:
            continue
        result.append(
            {
                "stock": f"{row['name']} {row['code']}",
                "type": "短線" if len(result) < 4 else "中線",
                "theme": row["theme"],
                "logic": f"法人合計買超 {fmt_signed_int(row['total'])} 股，外資 {fmt_signed_int(row['foreign'])} 股；若量能延續，可作為資金輪動觀察標的。",
                "technical": f"收盤 {row['close']}，日內區間 {row['low']}-{row['high']}；以不跌破前低作為續強判斷。",
                "entry": f"{fmt_float(close * 0.98)}-{fmt_float(close * 1.01)}",
                "stop": fmt_float(close * 0.95),
                "target": f"{fmt_float(close * 1.06)}-{fmt_float(close * 1.10)}",
                "risk": "若法人隔日轉賣或跌破 5 日線，應降槓桿並停止追價。",
            }
        )
        if len(result) >= 8:
            break
    return result


def strongest_sectors(market: dict, quotes: dict) -> list[dict]:
    sectors = sorted(market["sectors"], key=lambda row: to_float(row["pct"]), reverse=True)[:5]
    reps = {
        "半導體": "台積電、聯電、聯發科",
        "電子": "台積電、鴻海、台光電",
        "金融": "富邦金、國泰金、元大金",
        "航運": "長榮、陽明、萬海",
    }
    result = []
    for sector in sectors:
        name = sector["name"]
        representative = next((v for key, v in reps.items() if key in name), "以法人買超排行與量能突破股為主")
        result.append(
            {
                "name": name,
                "pct": sector["pct"],
                "reason": "漲幅領先大盤，顯示資金聚焦度提高。",
                "flow": "若同步出現在外資或投信買超排行，延續性較高；若僅指數反彈，隔日需看量能確認。",
                "continue": "偏正向，但不宜追高，等待回測不破短均線。",
                "representative": representative,
            }
        )
    return result


def render_rank_table(title: str, data: dict) -> str:
    rows = []
    for i in range(10):
        buy = data["buy"][i]
        sell = data["sell"][i]
        rows.append(
            f"""
            <tr>
              <td>{i + 1}</td>
              <td>{buy['name']} <span>{buy['code']}</span></td>
              <td class="pos">{fmt_signed_int(buy.get('total', buy.get('foreign', 0)) if title == '合計' else fmt_signed_int(0))}</td>
              <td>{sell['name']} <span>{sell['code']}</span></td>
              <td class="neg">{fmt_signed_int(sell.get('total', sell.get('foreign', 0)) if title == '合計' else fmt_signed_int(0))}</td>
            </tr>
            """
        )
    return "".join(rows)


def render_institution_table(label: str, column: str, data: dict) -> str:
    rows = []
    for i in range(10):
        buy = data["buy"][i]
        sell = data["sell"][i]
        rows.append(
            f"""
            <tr>
              <td>{i + 1}</td>
              <td>{buy['name']} <span>{buy['code']}</span></td>
              <td class="pos">{fmt_signed_int(buy[column])}</td>
              <td>{sell['name']} <span>{sell['code']}</span></td>
              <td class="neg">{fmt_signed_int(sell[column])}</td>
            </tr>
            """
        )
    return f"""
    <section class="card">
      <div class="card-head"><h3>{label}</h3><span>Top 10</span></div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>排名</th><th>買超</th><th>股數</th><th>賣超</th><th>股數</th></tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
    </section>
    """


def render_etf_holdings(etf: dict, quotes: dict) -> str:
    rows = []
    for item in etf["top_holdings"]:
        quote = quotes.get(item["code"], {})
        change = quote.get("change", "資料不足")
        close = quote.get("close", "資料不足")
        rows.append(
            f"""
            <tr>
              <td>{etf['code']}</td>
              <td>{item['name']} {item['code']}</td>
              <td>{item['weight']}</td>
              <td>{stock_theme(item['code'], item['name'])}</td>
              <td>{close} / {change}</td>
              <td>持股 {item['shares']}</td>
              <td>{'權重高，主導 ETF 淨值波動' if item == etf['top_holdings'][0] else '觀察是否與法人買超同步'}</td>
            </tr>
            """
        )
    return "".join(rows)


def render_html(market: dict, chips: dict, etf_a: dict, etf_b: dict) -> str:
    weighted = market["weighted"]
    move_class = pct_class(weighted["pct"])
    support = fmt_float(to_float(weighted["close"]) * 0.985)
    resistance = fmt_float(to_float(weighted["close"]) * 1.015)
    recs = recommendation_rows(chips, market["quotes"])
    sectors = strongest_sectors(market, market["quotes"])
    foreign_focus = chips["foreign"]["buy"][0]
    foreign_sell = chips["foreign"]["sell"][0]

    rec_rows = "".join(
        f"""
        <tr>
          <td>{row['stock']}</td><td>{row['type']} / {row['theme']}</td><td>{row['logic']}<br>{row['technical']}</td>
          <td>{row['entry']}</td><td>{row['stop']}</td><td>{row['target']}</td><td>{row['risk']}</td>
        </tr>
        """
        for row in recs
    )
    sector_rows = "".join(
        f"<tr><td>{s['name']}</td><td class='{pct_class(s['pct'])}'>{s['pct']}%</td><td>{s['reason']}</td><td>{s['flow']}</td><td>{s['continue']}</td><td>{s['representative']}</td></tr>"
        for s in sectors
    )
    source_links = "".join(
        f'<li><a href="{url}">{label}</a></li>' for label, url in GLOBAL_MARKET["sources"]
    )

    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
  <title>台股晨間投資報告 {REPORT_DATE}</title>
  <style>
    :root {{
      --navy:#0f172a; --blue:#38bdf8; --bg:#f8fafc; --line:#cbd5e1;
      --green:#10b981; --orange:#f59e0b; --red:#ef4444; --ink:#111827; --muted:#64748b;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:"Noto Sans TC","Microsoft JhengHei",Arial,sans-serif; background:var(--bg); color:var(--ink); line-height:1.65; }}
    .page {{ max-width:1180px; margin:0 auto; padding:20px 14px 48px; }}
    .hero {{ background:linear-gradient(135deg,#0f172a,#123052 58%,#0e7490); color:#fff; border-radius:8px; padding:24px; }}
    .badge {{ display:inline-flex; padding:5px 10px; border:1px solid rgba(255,255,255,.35); border-radius:999px; font-size:12px; color:#dbeafe; }}
    h1 {{ margin:12px 0 8px; font-size:32px; line-height:1.2; letter-spacing:0; }}
    h2 {{ margin:28px 0 12px; font-size:22px; color:var(--navy); }}
    h3 {{ margin:0; font-size:17px; color:var(--navy); }}
    .hero p {{ margin:0; max-width:920px; color:#e0f2fe; }}
    .kpis {{ display:grid; grid-template-columns:repeat(6,minmax(0,1fr)); gap:10px; margin-top:18px; }}
    .kpi {{ background:rgba(255,255,255,.1); border:1px solid rgba(255,255,255,.18); border-radius:8px; padding:12px; min-height:86px; }}
    .kpi span,.card-head span,.muted {{ color:var(--muted); font-size:12px; }}
    .kpi span {{ color:#bae6fd; }}
    .kpi strong {{ display:block; margin-top:4px; font-size:21px; color:#fff; }}
    .read-order {{ display:grid; grid-template-columns:repeat(3,1fr); gap:12px; background:#111827; border-radius:8px; padding:14px; margin-top:14px; }}
    .read-order div {{ color:#e5e7eb; }}
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
      <span class="badge">研究與決策支援，不保證投資報酬</span>
      <h1>台股晨間投資報告 {REPORT_DATE}</h1>
      <p>報告日為 {REPORT_DATE}，本版採用最新可取得的 {MARKET_RESULT_DATE} 台股收盤與法人資料，並納入 2026-06-22 美股收盤作為今日盤前國際市場參考。</p>
      <div class="kpis">
        <div class="kpi"><span>加權指數</span><strong>{weighted['close']}</strong></div>
        <div class="kpi"><span>日漲跌</span><strong class="{move_class}">{weighted['change']} / {weighted['pct']}%</strong></div>
        <div class="kpi"><span>台灣 50</span><strong>{market['tw50']['pct']}%</strong></div>
        <div class="kpi"><span>外資買超焦點</span><strong>{foreign_focus['name']}</strong></div>
        <div class="kpi"><span>外資賣超焦點</span><strong>{foreign_sell['name']}</strong></div>
        <div class="kpi"><span>美股關鍵</span><strong>費半 +2.04%</strong></div>
      </div>
    </section>

    <section class="read-order">
      <div><strong>1. 市場方向</strong><br>台股收盤轉強，盤前情緒偏多但非無風險。</div>
      <div><strong>2. 籌碼壓力</strong><br>追蹤外資是否延續買超，並避開單日大量賣超股。</div>
      <div><strong>3. ETF 策略</strong><br>00981A、00403A 均高度連動台積電與 AI 供應鏈。</div>
    </section>

    <h2>1. 今日市場結論</h2>
    <section class="card">
      <ul>
        <li>加權指數 {pct_word(weighted['pct'])} {weighted['pct']}%，短線氣氛偏多；但今日盤前美股科技大型股分歧，操作要等開盤量價確認。</li>
        <li>美股 6/22 費半續創高，對台積電、AI 伺服器、PCB、散熱與電源鏈偏正向；Nasdaq 回落則提醒高估值科技股不能無差別追價。</li>
        <li>外資買賣超需分辨 ETF 與現股：若買超集中在 ETF，代表資金偏配置；若同步買進半導體與 AI 零組件，才是主動風險承擔。</li>
        <li>今日可觀察支撐位約 {support}，壓力位約 {resistance}；若開高未放量，避免追價。</li>
        <li>盤勢預估：偏多震盪。短線只做回測承接，不做連續急漲後的高檔追單。</li>
      </ul>
    </section>

    <h2>2. 法人買賣超前 10 名</h2>
    <div class="grid">
      {render_institution_table("外資買賣超", "foreign", chips["foreign"])}
      {render_institution_table("投信買賣超", "trust", chips["trust"])}
      {render_institution_table("自營商買賣超", "dealer", chips["dealer"])}
      {render_institution_table("三大法人合計買賣超", "total", chips["total"])}
    </div>

    <h2>3. 大盤與國際市場影響</h2>
    <div class="grid">
      <section class="card">
        <div class="card-head"><h3>市場指數與技術判讀</h3><span>TWSE {MARKET_RESULT_DATE}</span></div>
        <ul>
          <li>加權指數趨勢：{weighted['close']}，{pct_word(weighted['pct'])} {weighted['change']} 點，短線偏多。</li>
          <li>OTC 趨勢：本次 TWSE API 未提供 OTC 即時欄位，需以櫃買中心最新資料交叉確認。</li>
          <li>台積電對大盤影響：台積電同時是 00981A、00403A 最大權重股，且費半續創高，對台股權值與 ETF 淨值均為關鍵。</li>
          <li>外資期貨未平倉方向：本次未取得 TAIFEX 未平倉資料，列為待確認；現貨外資流向先作為替代觀察。</li>
          <li>台幣匯率影響：資料不足；若台幣走強，有利外資回補權值股，若快速貶值則壓抑估值。</li>
          <li>市場情緒：偏多震盪。支撐 {support}，壓力 {resistance}。</li>
        </ul>
      </section>
      <section class="card">
        <div class="card-head"><h3>國際市場直接影響</h3><span>{GLOBAL_MARKET['date']}</span></div>
        <div class="alert good">{GLOBAL_MARKET['headline']}</div>
        <ul>{"".join(f"<li>{item}</li>" for item in GLOBAL_MARKET["items"])}</ul>
      </section>
    </div>

    <h2>4. 強勢族群</h2>
    <section class="card">
      <div class="table-wrap">
        <table>
          <thead><tr><th>族群</th><th>漲跌幅</th><th>為何強勢</th><th>資金流入原因</th><th>延續性</th><th>代表股</th></tr></thead>
          <tbody>{sector_rows}</tbody>
        </table>
      </div>
    </section>

    <h2>5. ETF 00981A / 00403A 每日成分股報告</h2>
    <section class="card">
      <div class="card-head"><h3>{etf_a['code']} {etf_a['name']}</h3><span>更新 {etf_a['updated']}</span></div>
      <div class="alert">市價 {etf_a['price']}，漲跌 {etf_a['change']}（{etf_a['pct']}）；NAV {etf_a['nav']}，折溢價 {etf_a['premium']}%。前十大集中度約 {fmt_float(sum(to_float(h['weight']) for h in etf_a['top_holdings']))}% 。</div>
      <div class="table-wrap"><table><thead><tr><th>ETF</th><th>成分股</th><th>權重</th><th>族群</th><th>今日表現</th><th>籌碼/量能</th><th>解讀</th></tr></thead><tbody>{render_etf_holdings(etf_a, market['quotes'])}</tbody></table></div>
    </section>
    <section class="card">
      <div class="card-head"><h3>{etf_b['code']} {etf_b['name']}</h3><span>更新 {etf_b['updated']}</span></div>
      <div class="alert">市價 {etf_b['price']}，漲跌 {etf_b['change']}（{etf_b['pct']}）；NAV {etf_b['nav']}，折溢價 {etf_b['premium']}%。前十大集中度約 {fmt_float(sum(to_float(h['weight']) for h in etf_b['top_holdings']))}% 。</div>
      <div class="table-wrap"><table><thead><tr><th>ETF</th><th>成分股</th><th>權重</th><th>族群</th><th>今日表現</th><th>籌碼/量能</th><th>解讀</th></tr></thead><tbody>{render_etf_holdings(etf_b, market['quotes'])}</tbody></table></div>
    </section>
    <section class="card">
      <div class="table-wrap">
        <table>
          <thead><tr><th>ETF</th><th>今日觀察</th><th>適合情境</th><th>風險</th><th>操作建議</th></tr></thead>
          <tbody>
            <tr><td>00981A</td><td>主動成長配置，台積電與 AI 供應鏈權重高。</td><td>偏多盤、科技股輪動盤。</td><td>成分集中，若費半回落或台積電開高走低，淨值波動放大。</td><td>已有持倉續抱；新資金分批，不追單日長紅。</td></tr>
            <tr><td>00403A</td><td>升級 50 型配置，台積電權重更高。</td><td>想用 ETF 參與大型權值股反彈。</td><td>對台積電與大型電子股依賴較高，分散度低於廣泛型 ETF。</td><td>適合核心衛星中的成長衛星部位，跌回短均附近再加碼。</td></tr>
          </tbody>
        </table>
      </div>
    </section>

    <h2>6. 潛力個股 / 追蹤清單</h2>
    <section class="card">
      <div class="table-wrap">
        <table>
          <thead><tr><th>股票</th><th>類型</th><th>邏輯</th><th>進場區</th><th>停損</th><th>目標價</th><th>風險</th></tr></thead>
          <tbody>{rec_rows}</tbody>
        </table>
      </div>
    </section>

    <h2>7. ETF 配置與今日交易策略</h2>
    <div class="grid">
      <section class="card">
        <div class="table-wrap">
          <table>
            <thead><tr><th>ETF</th><th>類型</th><th>建議原因</th><th>配置建議</th></tr></thead>
            <tbody>
              <tr><td>00981A</td><td>成長型 / AI 相關</td><td>主動式成長，受 AI 與半導體資金偏好支撐。</td><td>積極型 15%-20%，穩健型 8%-12%。</td></tr>
              <tr><td>00403A</td><td>大型權值 / AI 相關</td><td>台積電權重高，適合權值反彈情境。</td><td>積極型 10%-15%，穩健型 5%-10%。</td></tr>
              <tr><td>0050 / 市值型</td><td>防禦核心</td><td>降低單一主題集中度。</td><td>保守型 20%-35%。</td></tr>
              <tr><td>高股息 ETF</td><td>高股息 / 防禦</td><td>市場高檔震盪時提供現金流與波動緩衝。</td><td>保守型 20%-30%，不追溢價。</td></tr>
            </tbody>
          </table>
        </div>
      </section>
      <section class="card">
        <ul>
          <li>保守型策略：股票與成長 ETF 合計 40%-50%，現金 50%-60%；關注 0050、高股息 ETF、台積電回測承接。</li>
          <li>穩健型策略：股票與 ETF 合計 55%-65%，以 00981A / 00403A 分批配置，搭配半導體與散熱龍頭。</li>
          <li>積極型策略：70% 以內，聚焦法人買超且放量突破股；若開高走低，當日不加碼。</li>
          <li>適合操作週期：短線 1-5 日只看量價與法人延續；中線 2-6 週看 AI 資本支出與費半趨勢。</li>
        </ul>
      </section>
    </div>

    <h2>8. 今日風險提醒</h2>
    <section class="card">
      <div class="alert risk">最大風險：台股前一日強漲後，今日若開高但量能無法延續，容易出現獲利了結；同時美股科技大型股轉弱，可能壓抑追價意願。</div>
      <ul>
        <li>可能利空：Fed 偏鷹談話、美元或美債殖利率再度上行、AI 股估值過熱後回檔。</li>
        <li>市場過熱訊號：成交量放大但指數開高走低、外資現貨轉賣、ETF 折溢價快速擴大。</li>
        <li>不建議追價族群：單日急漲且無法人延續買超的小型題材股、短線漲幅遠高於基本面更新的 AI 零組件。</li>
        <li>拉回原因：台積電與費半若無法延續，台股權值與 00981A / 00403A 將同步受壓。</li>
      </ul>
    </section>

    <footer class="footer">
      <p>固定公開網址：<a href="{PUBLIC_URL}">{PUBLIC_URL}</a></p>
      <p>資料來源：TWSE MI_INDEX、TWSE T86、ETF 資訊網 00981A / 00403A 成分股頁；國際市場參考：</p>
      <ul>{source_links}</ul>
      <p>本報告為研究與決策支援，不保證投資報酬；實際交易請依個人風險承受度與最新盤中資訊調整。</p>
    </footer>
  </main>
</body>
</html>
"""


def build_line_message(market: dict, chips: dict, etf_a: dict, etf_b: dict) -> str:
    weighted = market["weighted"]
    return (
        f"台股晨報 {REPORT_DATE}\n"
        f"採用最新交易資料：{MARKET_RESULT_DATE}\n\n"
        f"1. 加權指數 {weighted['close']}，{pct_word(weighted['pct'])} {weighted['change']} 點（{weighted['pct']}%），盤勢偏多震盪。\n"
        "2. 美股 6/22 漲跌互見：S&P 500 -0.37%、Nasdaq -1.32%、Dow +0.29%，費半 +2.04%續創高；台股半導體偏正向，但科技股追價要保守。\n"
        f"3. 外資買超焦點：{chips['foreign']['buy'][0]['name']}；外資賣超焦點：{chips['foreign']['sell'][0]['name']}，今日需確認是否延續。\n"
        f"4. 00981A 市價 {etf_a['price']}、前十大集中度約 {fmt_float(sum(to_float(h['weight']) for h in etf_a['top_holdings']))}%；00403A 市價 {etf_b['price']}、前十大集中度約 {fmt_float(sum(to_float(h['weight']) for h in etf_b['top_holdings']))}%。\n"
        "5. 策略：保守者等回測，穩健者分批配置 ETF，積極者只追法人買超且放量延續股；開高走低不加碼。\n\n"
        f"完整報告：{PUBLIC_URL}\n"
        "提醒：本內容為研究與決策支援，不保證投資報酬。"
    )


def write_outputs(report_html: str, line_text: str) -> None:
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "index.html").write_text(report_html, encoding="utf-8")
    (ROOT / "reports" / f"{REPORT_DATE}.html").write_text(report_html, encoding="utf-8")

    index_path = ROOT / "reports" / "index.json"
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
    report_html = render_html(market, chips, etf_a, etf_b)
    line_text = build_line_message(market, chips, etf_a, etf_b)
    write_outputs(report_html, line_text)
    print(json.dumps({"report_date": REPORT_DATE, "market_result_date": MARKET_RESULT_DATE}, ensure_ascii=False))


if __name__ == "__main__":
    main()
