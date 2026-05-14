"""
均線回踩選股
邏輯：近二個月內（約 42 交易日）曾符合熱門股條件（放寬版），
      且現價在以下任一均線的 ±2% 以內：
  Type1 - 60MA  ±2%
  Type2 - 120MA ±2%
"""
from dotenv import load_dotenv
load_dotenv()

import os, sys, io, json, webbrowser
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR.parent / "熱門股追蹤"))
WATCHLIST_HTML = SCRIPT_DIR.parent / "Watchlist" / "stock_watchlist.html"

import pandas as pd
import numpy as np
from finlab import data
from theme_map import THEME

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── 參數（放寬版）────────────────────────────────────────────
PERCENTILE_MIN   = 0.65   # 原 0.75
N_HIST           = 252
ACCEL_MIN        = 0.60   # 原 0.75
RET_5D_MIN       = -0.03  # 允許小幅回檔（原 0.0）
MARKET_CAP_MIN   = 20e8   # 放寬至 20 億（原 30 億）
TURNOVER_ABS_MIN = 10e8   # 放寬至 10 億（原 30 億）
LOOKBACK_DAYS    = 42     # 約二個月
MA_TOL           = 0.02   # ±2%
# ─────────────────────────────────────────────────────────────

print("載入資料中...")
close        = data.get("price:收盤價")
turnover_raw = data.get("price:成交金額")
market_value = data.get("etl:market_value")

latest_date = close.index[-1]
today_str   = str(latest_date.date())
print(f"分析日期：{today_str}")

def load_twse_codes():
    try:
        text = WATCHLIST_HTML.read_text(encoding="utf-8")
        import re
        m = re.search(r"let embeddedTWSECodes\s*=\s*(\[.*?\]);", text, re.DOTALL)
        return json.loads(m.group(1)) if m else []
    except Exception as exc:
        print(f"[WARN] 無法讀取上市代碼清單，TradingView 預設使用 TWSE：{exc}")
        return []

twse_codes_json = json.dumps(load_twse_codes(), ensure_ascii=False, separators=(",", ":"))

# ── 換手率 ────────────────────────────────────────────────────
turnover_rate = turnover_raw.div(market_value)

# ── 熱度百分位（在 252 日窗口內逐日排名）────────────────────────
turn_rate_3d = turnover_rate.rolling(3, min_periods=2).sum()
hist_window  = turn_rate_3d.iloc[-N_HIST:]
hot_pct_all  = hist_window.rank(pct=True)           # (N_HIST, n_stocks)
hot_pct_win  = hot_pct_all.iloc[-LOOKBACK_DAYS:]    # (42, n_stocks)

# ── 加速比（逐日）────────────────────────────────────────────
# accel[d] = sum(turnover_rate[d-2:d+1]) / sum(turnover_rate[d-5:d-2])
accel_all = turn_rate_3d / turn_rate_3d.shift(3)
accel_win = accel_all.iloc[-LOOKBACK_DAYS:]

# ── 5日報酬（逐日）──────────────────────────────────────────
ret_5d_all = close.pct_change(5, fill_method=None)
ret_5d_win = ret_5d_all.iloc[-LOOKBACK_DAYS:]

# ── 成交值 & 市值（逐日）────────────────────────────────────
turnover_win = turnover_raw.iloc[-LOOKBACK_DAYS:]
mktcap_win   = market_value.iloc[-LOOKBACK_DAYS:]

# ── 每日 mask → 取 42 天內任一天符合所有條件 ─────────────────
daily_mask = (
    (hot_pct_win  >= PERCENTILE_MIN) &
    (accel_win    >= ACCEL_MIN) &
    (ret_5d_win   >= RET_5D_MIN) &
    (turnover_win >= TURNOVER_ABS_MIN) &
    (mktcap_win   >= MARKET_CAP_MIN)
)

# 篩選合法股票代碼（4 碼、非 0 字頭）
valid_cols = [c for c in daily_mask.columns if len(c) == 4 and not c.startswith("0")]
daily_mask = daily_mask[valid_cols]

qualified_any    = daily_mask.any()
qualified_stocks = qualified_any[qualified_any].index.tolist()
print(f"近二個月曾達標股票數：{len(qualified_stocks)} 檔")

# ── 每支股票：最近達標日、最高熱度百分位、最大加速比 ────────────
last_qualify = {}
best_hot     = {}
best_acc     = {}
for sid in qualified_stocks:
    days_ok = daily_mask[sid]
    last_qualify[sid] = str(days_ok[days_ok].index[-1].date())
    if sid in hot_pct_win.columns:
        best_hot[sid] = float(hot_pct_win[sid][days_ok].max())
    if sid in accel_win.columns:
        best_acc[sid] = float(accel_win[sid][days_ok].max())

# ── MA60 / MA120 現值 ─────────────────────────────────────────
ma60_all  = close.rolling(60,  min_periods=30).mean()
ma120_all = close.rolling(120, min_periods=60).mean()
ma60  = ma60_all.iloc[-1]
ma120 = ma120_all.iloc[-1]
price = close.iloc[-1]

# ── 過去二個月收盤 > 120MA 的天數 ────────────────────────────
above120_days = (close.iloc[-LOOKBACK_DAYS:] > ma120_all.iloc[-LOOKBACK_DAYS:]).sum()
above120_days = above120_days.reindex(valid_cols)
ret1  = close.pct_change(1, fill_method=None).iloc[-1]
ret5  = ret_5d_all.iloc[-1]

# ── 公司資訊 ──────────────────────────────────────────────────
company_info = data.get("company_basic_info")
stock_name = (
    company_info.set_index("stock_id")[company_info.columns[2]]
    .str.replace(r"股份有限公司|有限公司", "", regex=True).str.strip()
)
broad_cat = company_info.set_index("stock_id")[company_info.columns[3]]

BROAD_MAP = {
    "半導體業": "半導體", "電子零組件業": "電子零組件", "光電業": "光電",
    "電腦及週邊設備業": "電腦週邊", "通信網路業": "網通", "電機機械": "電機",
    "其他電子業": "其他電子", "電子通路業": "電子通路", "資訊服務業": "資訊服務",
    "數位雲端": "數位雲端", "生技醫療業": "生技醫療", "化學工業": "化學",
    "汽車工業": "汽車電子", "機械工業": "機械", "綠能環保": "綠能",
}

def map_theme(sid):
    t = THEME.get(sid, "")
    if not t:
        b = broad_cat.get(sid, "")
        t = BROAD_MAP.get(b, b)
    return t

# ── 組建結果表 ────────────────────────────────────────────────
base = pd.DataFrame({
    "price":      price.reindex(qualified_stocks),
    "ma60":       ma60.reindex(qualified_stocks),
    "ma120":      ma120.reindex(qualified_stocks),
    "ret_1d":     ret1.reindex(qualified_stocks),
    "ret_5d":     ret5.reindex(qualified_stocks),
    "turnover":   turnover_raw.iloc[-1].reindex(qualified_stocks),
    "market_cap": market_value.iloc[-1].reindex(qualified_stocks),
}).dropna(subset=["price"])

base["name"]        = base.index.map(lambda x: stock_name.get(x, x))
base["theme"]       = base.index.map(map_theme)
base["dist60"]      = base["price"] / base["ma60"]  - 1
base["dist120"]     = base["price"] / base["ma120"] - 1
base["last_date"]   = base.index.map(lambda x: last_qualify.get(x, "-"))
base["best_hot"]    = base.index.map(lambda x: best_hot.get(x, float("nan")))
base["best_accel"]  = base.index.map(lambda x: best_acc.get(x, float("nan")))
base["above120_d"]  = above120_days.reindex(base.index)

# ── Type1 & Type2 ────────────────────────────────────────────
# 共同條件：過去二個月收盤 > 120MA 天數 > 20
above120_ok = base["above120_d"] > 20

type1 = (base[above120_ok & base["ma60"].notna()  & (base["dist60"].abs()  <= MA_TOL)]
             .sort_values("best_hot", ascending=False))
type2 = (base[above120_ok & base["ma120"].notna() & (base["dist120"].abs() <= MA_TOL)]
             .sort_values("best_hot", ascending=False))

print(f"Type1（60MA ±2%）：{len(type1)} 檔")
print(f"Type2（120MA ±2%）：{len(type2)} 檔")

# ── 終端機輸出 ────────────────────────────────────────────────
HDR = f"{'代號':6} {'名稱':14} {'主題':12} {'現價':>8} {'均線':>9} {'偏離':>7} {'>120MA天':>8} {'最近達標':>12} {'最高熱度':>8} {'最大加速':>8} {'1日':>6} {'5日':>7}"
SEP = "─" * 106

def print_section(df, ma_col, dist_col, label):
    print(f"\n{SEP}")
    print(f"  {label}  回踩（±2%，近2月收盤>120MA天數>20）：{len(df)} 檔")
    print(SEP)
    print(HDR)
    print(SEP)
    for sid, row in df.iterrows():
        ma_v   = row[ma_col]
        ma_s   = f"{ma_v:.2f}" if pd.notna(ma_v) else "-"
        dist   = row[dist_col]
        dist_s = f"{dist:+.1%}" if pd.notna(dist) else "-"
        ad     = int(row["above120_d"]) if pd.notna(row["above120_d"]) else "-"
        print(f"{sid:6} {row['name'][:12]:14} {row['theme']:12} "
              f"{row['price']:>8.2f} {ma_s:>9} {dist_s:>7} {str(ad):>8} "
              f"{row['last_date']:>12} "
              f"{row['best_hot']:>8.0%} {row['best_accel']:>8.2f}x "
              f"{row['ret_1d']:>+6.1%} {row['ret_5d']:>+7.1%}")

print_section(type1, "ma60",  "dist60",  "第一種：60MA")
print_section(type2, "ma120", "dist120", "第二種：120MA")

# ═══════════════════════════════════════════════════════════
#  HTML 輸出
# ═══════════════════════════════════════════════════════════
THEME_COLOR = {
    "晶圓代工": "#1565c0", "IC設計": "#1976d2", "封裝測試": "#0288d1",
    "矽晶圓": "#0d47a1", "功率半導體": "#283593", "記憶體": "#01579b",
    "記憶體模組": "#0277bd", "PCB/載板": "#1a237e",
    "伺服器/AI": "#880e4f", "散熱": "#ad1457", "電源": "#c62828",
    "EMS/代工": "#b71c1c", "連接器": "#6a1b9a",
    "網通": "#00695c", "電腦週邊": "#2e7d32",
    "面板": "#e65100", "光電/LED": "#f57f17", "光電": "#ff6f00",
    "被動元件": "#4e342e", "品牌PC/NB": "#37474f", "電子通路": "#455a64",
    "半導體": "#1b5e20", "電子零組件": "#33691e", "其他電子": "#424242",
    "電機": "#4a148c", "資訊服務": "#006064", "數位雲端": "#1565c0",
    "汽車電子": "#bf360c", "生技醫療": "#1a6b3a", "化學": "#5d4037",
    "機械": "#546e7a", "綠能": "#2e7d32",
}

def pct_col(v):
    if pd.isna(v): return "#8b949e"
    if v >= 0.15: return "#00e676"
    if v >= 0.05: return "#69f0ae"
    if v >= 0.01: return "#b9f6ca"
    if v >= 0:    return "#c8e6c9"
    if v >= -0.05: return "#ff8a80"
    return "#ff5252"

def dist_col(v):
    if pd.isna(v): return "#8b949e"
    pct = abs(v)
    if pct <= 0.005: return "#00e676"    # 非常接近
    if pct <= 0.01:  return "#69f0ae"    # 很近
    if pct <= 0.015: return "#ffab40"    # 略遠
    return "#ff8a80"                      # 接近邊界

def hot_col(v):
    if pd.isna(v): return "#8b949e"
    if v >= 0.90: return "#00e676"
    if v >= 0.80: return "#69f0ae"
    if v >= 0.65: return "#ffab40"
    return "#8b949e"

def theme_badge(t):
    bg = THEME_COLOR.get(t, "#21262d")
    return (f'<span style="background:{bg};color:white;padding:2px 7px;'
            f'border-radius:10px;font-size:0.76rem;white-space:nowrap">{t}</span>')

def build_rows(df, ma_col, dist_col_name):
    rows = []
    for sid, row in df.iterrows():
        ma_v   = row[ma_col]
        ma_s   = f"{ma_v:.2f}" if pd.notna(ma_v) else "-"
        dist_v = row[dist_col_name]
        dist_s = f"{dist_v:+.2%}" if pd.notna(dist_v) else "-"
        tv     = f"{row['turnover']/1e8:.0f}億" if pd.notna(row["turnover"]) else "-"
        mc     = row["market_cap"]
        mc_s   = (f"{mc/1e12:.1f}兆" if pd.notna(mc) and mc >= 1e12
                  else (f"{mc/1e8:.0f}億" if pd.notna(mc) else "-"))
        dc     = dist_col(dist_v)
        ad     = int(row["above120_d"]) if pd.notna(row["above120_d"]) else "-"
        ad_col = "#00e676" if isinstance(ad, int) and ad >= 30 else ("#69f0ae" if isinstance(ad, int) and ad >= 25 else "#ffab40")
        name_js = row['name'].replace("'", "").replace('"', "")
        rows.append(f"""<tr>
          <td style="font-weight:700;color:#58a6ff;cursor:pointer;text-decoration:underline dotted"
              onclick="openChart('{sid}','{name_js}')" title="點擊查看 {name_js} K線圖">{sid}</td>
          <td>{row['name']}</td>
          <td>{theme_badge(row['theme'])}</td>
          <td style="text-align:right;font-weight:600">{row['price']:.2f}</td>
          <td style="text-align:right;color:#8b949e">{ma_s}</td>
          <td style="text-align:right;color:{dc};font-weight:700">{dist_s}</td>
          <td style="text-align:right;color:{ad_col};font-weight:600">{ad}</td>
          <td style="text-align:right;color:#8b949e">{mc_s}</td>
          <td style="text-align:right;color:#58a6ff">{tv}</td>
          <td style="text-align:right;color:{hot_col(row['best_hot'])};font-weight:600">{row['best_hot']:.0%}</td>
          <td style="text-align:right;color:#8b949e">{row['best_accel']:.2f}x</td>
          <td style="text-align:right;color:#8b949e;font-size:0.8rem">{row['last_date']}</td>
          <td style="text-align:right;color:{pct_col(row['ret_1d'])};font-weight:600">{row['ret_1d']:+.1%}</td>
          <td style="text-align:right;color:{pct_col(row['ret_5d'])};font-weight:600">{row['ret_5d']:+.1%}</td>
        </tr>""")
    return "\n".join(rows)

THEAD = """<thead><tr>
  <th>代號</th><th>名稱</th><th>主題</th>
  <th style="text-align:right">現價</th>
  <th style="text-align:right">均線</th>
  <th style="text-align:right">偏離</th>
  <th style="text-align:right">&gt;120MA天數<br><small style="font-weight:400;color:#8b949e">近2月</small></th>
  <th style="text-align:right">市值</th>
  <th style="text-align:right">成交值</th>
  <th style="text-align:right">最高熱度</th>
  <th style="text-align:right">最大加速</th>
  <th style="text-align:right">最近達標日</th>
  <th style="text-align:right">1日</th>
  <th style="text-align:right">5日</th>
</tr></thead>"""

rows1 = build_rows(type1, "ma60",  "dist60")
rows2 = build_rows(type2, "ma120", "dist120")

html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<title>均線回踩選股 {today_str}</title>
<style>
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ background:#0d1117; color:#e6edf3; font-family:'Segoe UI','Microsoft JhengHei',sans-serif; padding:20px 28px; }}
h1 {{ font-size:1.4rem; color:#58a6ff; margin-bottom:6px; }}
h2 {{ color:#58a6ff; margin:32px 0 10px; font-size:1.05rem; border-left:3px solid #58a6ff; padding-left:10px; }}
.sub {{ color:#8b949e; font-size:0.84rem; margin-bottom:24px; line-height:1.9; }}
.params {{ display:flex; flex-wrap:wrap; gap:8px; margin-bottom:24px; }}
.param {{ background:#161b22; border:1px solid #30363d; border-radius:6px; padding:6px 12px; font-size:0.8rem; color:#8b949e; }}
.param span {{ color:#e6edf3; font-weight:600; }}
.count-badge {{ display:inline-block; background:#1f6feb; color:white; border-radius:12px; padding:2px 10px; font-size:0.8rem; margin-left:8px; }}
table {{ width:100%; border-collapse:collapse; font-size:0.86rem; margin-bottom:32px; }}
th {{ background:#161b22; color:#8b949e; padding:8px 12px; text-align:left; position:sticky; top:0; border-bottom:1px solid #30363d; white-space:nowrap; font-weight:600; }}
td {{ padding:6px 12px; border-bottom:1px solid #1c2128; white-space:nowrap; }}
tr:hover td {{ background:#1c2128; }}
input#search {{ background:#161b22; border:1px solid #30363d; border-radius:6px; padding:6px 12px; color:#e6edf3; font-size:0.88rem; width:240px; margin-bottom:10px; }}
input#search::placeholder {{ color:#484f58; }}
.note {{ background:#161b22; border:1px solid #30363d; border-radius:8px; padding:14px 16px; margin-bottom:20px; font-size:0.84rem; color:#8b949e; line-height:1.9; }}
.footer {{ margin-top:32px; color:#484f58; font-size:0.76rem; text-align:center; line-height:2; }}
</style>
</head>
<body>
<h1>均線回踩選股</h1>
<div class="sub">
  {latest_date.strftime('%Y年%m月%d日')} &nbsp;|&nbsp;
  近二個月（{LOOKBACK_DAYS} 交易日）曾達熱門條件 &nbsp;|&nbsp;
  現價落在均線 ±{MA_TOL*100:.0f}% 以內<br>
  <span style="color:#484f58">
  近二個月達標股票：{len(qualified_stocks)} 檔 &rarr;
  Type1（60MA±2%）{len(type1)} 檔 &nbsp; Type2（120MA±2%）{len(type2)} 檔
  </span>
</div>

<div class="params">
  <div class="param">熱度百分位 &ge; <span>{PERCENTILE_MIN:.0%}</span>（原 75%）</div>
  <div class="param">加速比 &ge; <span>{ACCEL_MIN}</span>（原 0.75）</div>
  <div class="param">5日報酬 &ge; <span>{RET_5D_MIN:+.0%}</span>（允許回檔）</div>
  <div class="param">市值 &ge; <span>{MARKET_CAP_MIN/1e8:.0f}億</span>（原 30億）</div>
  <div class="param">成交值 &ge; <span>{TURNOVER_ABS_MIN/1e8:.0f}億</span>（原 30億）</div>
  <div class="param">有效期 <span>近 {LOOKBACK_DAYS} 交易日（約二個月）</span></div>
</div>

<div class="note">
  <b>偏離含義：</b>正值 = 現價高於均線，負值 = 現價低於均線。<br>
  <b>最高熱度：</b>近二個月達標期間的最高歷史熱度百分位（越高代表當時量能越強）。<br>
  <b>最大加速：</b>近二個月達標期間的最高加速比（近3日換手率之和 ÷ 前3日之和）。<br>
  <b>最近達標日：</b>最近一次同時滿足所有熱門條件的日期（越近越好）。
</div>

<input type="text" id="search" placeholder="搜尋代號 / 名稱 / 主題...">

<h2>第一種：現價在 60MA ±2% 以內 <span class="count-badge">{len(type1)} 檔</span></h2>
<table id="tbl1">
  {THEAD}
  <tbody>{rows1}</tbody>
</table>

<h2>第二種：現價在 120MA ±2% 以內 <span class="count-badge">{len(type2)} 檔</span></h2>
<table id="tbl2">
  {THEAD}
  <tbody>{rows2}</tbody>
</table>

<div class="footer">
  篩選參數：歷史熱度百分位≥{PERCENTILE_MIN:.0%}、加速比≥{ACCEL_MIN}、5日報酬≥{RET_5D_MIN:+.0%}、
  成交值≥{TURNOVER_ABS_MIN/1e8:.0f}億、市值≥{MARKET_CAP_MIN/1e8:.0f}億、有效期近{LOOKBACK_DAYS}交易日<br>
  均線偏離容差 ±{MA_TOL*100:.0f}%　主題分類見 theme_map.py
</div>

<script>
const embeddedTWSECodes = new Set({twse_codes_json});
function openChart(sid, name) {{
    var code = String(sid);
    var ex = embeddedTWSECodes.size === 0 ? 'TWSE' : (embeddedTWSECodes.has(code) ? 'TWSE' : 'TPEX');
    var url = 'https://www.tradingview.com/chart/?symbol=' + ex + ':' + code;
    window.open(url, 'kline_' + sid,
        'width=1280,height=800,resizable=yes,toolbar=no,location=yes,menubar=no,status=no');
}}
document.getElementById('search').addEventListener('input', function() {{
  var q = this.value.toLowerCase();
  ['tbl1','tbl2'].forEach(function(id) {{
    document.querySelectorAll('#' + id + ' tbody tr').forEach(function(tr) {{
      tr.style.display = tr.innerText.toLowerCase().includes(q) ? '' : 'none';
    }});
  }});
}});
</script>
</body>
</html>"""

out_path = str(SCRIPT_DIR / f"均線回踩選股_{today_str}.html")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(html)
print(f"\nHTML 已輸出：{out_path}")
webbrowser.open(f"file:///{out_path.replace(chr(92), '/')}")
