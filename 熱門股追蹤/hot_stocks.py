"""
熱門股追蹤表
選股：歷史熱度百分位 × 加速比 × 5日報酬
擴散：每個主題的參與率、漲停數、週間趨勢、宏觀族群擴散偵測
"""
from dotenv import load_dotenv
load_dotenv()

import os, sys, io, json, webbrowser
from html import escape
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from finlab import data
from theme_map import THEME

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── 參數 ──────────────────────────────────────────────────
PERCENTILE_MIN   = 0.75   # 歷史熱度百分位門檻（75% = 過去一年中前25%）
N_HIST           = 252    # 歷史回顧天數（約1年）
ACCEL_MIN        = 0.75   # 加速比門檻
RET_5D_MIN       = 0.0    # 5日報酬門檻
MARKET_CAP_MIN   = 30e8   # 市值門檻（30億）
TURNOVER_ABS_MIN = 30e8   # 今日絕對成交值（流動性門檻，30億）
TOP_N            = 20
HISTORY_DIR      = Path(__file__).parent / "history"
WATCHLIST_HTML   = Path(__file__).parent.parent / "Watchlist" / "stock_watchlist.html"

MACRO_GROUPS = {
    "半導體供應鏈": {"晶圓代工","IC設計","封裝測試","矽晶圓","功率半導體","記憶體","記憶體模組","PCB/載板"},
    "AI/伺服器鏈":  {"伺服器/AI","散熱","電源","EMS/代工","連接器"},
    "網通/通訊鏈":  {"網通","連接器","電腦週邊"},
    "面板/光電鏈":  {"面板","光電/LED","光電"},
}
# ─────────────────────────────────────────────────────────

print("載入資料中...")
close = data.get("price:收盤價")

# 若本地資料不含最近交易日，強制從雲端更新
from datetime import date as _date, timedelta as _td
_prev = _date.today() - _td(days=1)
while _prev.weekday() >= 5:
    _prev -= _td(days=1)
if close.index[-1].date() < _prev:
    print("本地資料過期，強制從雲端更新...")
    data.force_cloud_download = True
    close = data.get("price:收盤價")

turnover_raw = data.get("price:成交金額")
market_value = data.get("etl:market_value")

ret_1d = close.pct_change(1, fill_method=None)
ret_5d = close.pct_change(5, fill_method=None)
ret_20d = close.pct_change(20, fill_method=None)

# 放量位置：現價 / 三年高點（0~1，越低表示在低檔區放量）
price_3yh = close.iloc[-756:].max()
price_pos  = (close.iloc[-1] / price_3yh).clip(upper=1.0)

# 月內位置：(現價 - 月內最低) / (月內最高 - 月內最低)
_m_low  = close.iloc[-21:].min()
_m_high = close.iloc[-21:].max()
month_pos = ((close.iloc[-1] - _m_low) / (_m_high - _m_low).replace(0, np.nan)).clip(0, 1)

# ── TurnoverShock ────────────────────────────
# 換手率 = 成交額 / 流通市值，消除大小市值差異
# 近3日換手率加總，在過去 N_HIST 個交易日中的百分位排名
turnover_rate        = turnover_raw.div(market_value)
turn_rate_3d_rolling = turnover_rate.rolling(3, min_periods=2).sum()
hist_window          = turn_rate_3d_rolling.iloc[-N_HIST:]
hot_pct              = hist_window.rank(pct=True).iloc[-1]   # 0.0 ~ 1.0

# 加速比：近3日換手率合計 / 前3日換手率合計（方向性）
turn_3d_sum   = turnover_rate.iloc[-3:].sum()
turn_prev_sum = turnover_rate.iloc[-6:-3].sum()
accel         = turn_3d_sum / turn_prev_sum.replace(0, np.nan)

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

# ── 公司資訊 ──────────────────────────────────────────────
company_info = data.get("company_basic_info")
data.force_cloud_download = False
stock_name = (
    company_info.set_index("stock_id")[company_info.columns[2]]
    .str.replace(r"股份有限公司|有限公司", "", regex=True).str.strip()
)
broad_cat = company_info.set_index("stock_id")[company_info.columns[3]]

BROAD_MAP = {
    "半導體業":         "半導體",
    "電子零組件業":     "電子零組件",
    "光電業":           "光電",
    "電腦及週邊設備業": "電腦週邊",
    "通信網路業":       "網通",
    "電機機械":         "電機",
    "其他電子業":       "其他電子",
    "電子通路業":       "電子通路",
    "資訊服務業":       "資訊服務",
    "數位雲端":         "數位雲端",
    "生技醫療業":       "生技醫療",
    "化學工業":         "化學",
    "汽車工業":         "汽車電子",
    "機械工業":         "機械",
    "綠能環保":         "綠能",
}
KEEP_THEMES = {
    "晶圓代工","矽晶圓","IC設計","功率半導體","記憶體","記憶體模組",
    "封裝測試","PCB/載板","被動元件","散熱","伺服器/AI","EMS/代工",
    "電源","網通","連接器","面板","光電/LED","品牌PC/NB","電子通路",
    "半導體","電子零組件","光電","電腦週邊","其他電子","電機",
    "資訊服務","數位雲端","汽車電子",
}

def map_theme(sid):
    t = THEME.get(sid, "")
    if not t:
        b = broad_cat.get(sid, "")
        t = BROAD_MAP.get(b, b)
    return t

# ═══════════════════════════════════════════════════════════
#  股票宇宙（擴散分母）
# ═══════════════════════════════════════════════════════════
base = pd.DataFrame({
    "ret_1d":   ret_1d.iloc[-1],
    "ret_5d":   ret_5d.iloc[-1],
    "hot_pct":  hot_pct,
    "accel":    accel,
    "turnover": turnover_raw.iloc[-1],
    "market_cap": market_value.iloc[-1],
}).dropna(subset=["ret_1d", "ret_5d", "hot_pct", "accel"])

base = base[~base.index.str.startswith("0")]
base = base[base.index.str.len() == 4]
base["name"]  = base.index.map(lambda x: stock_name.get(x, x))
base["theme"] = base.index.map(map_theme)
base = base[base["theme"].isin(KEEP_THEMES)]

theme_total = base.groupby("theme").size().rename("total")
limit_up_by_theme = (
    base[base["ret_1d"] >= 0.095]
    .groupby("theme").size()
    .rename("limit_up")
)

# ═══════════════════════════════════════════════════════════
#  熱門股篩選
# ═══════════════════════════════════════════════════════════
df = base[base["market_cap"].fillna(0) >= MARKET_CAP_MIN].copy()
mask = (
    (df["hot_pct"]  >= PERCENTILE_MIN) &
    (df["accel"]    >= ACCEL_MIN) &
    (df["ret_5d"]   >= RET_5D_MIN) &
    (df["turnover"].fillna(0) >= TURNOVER_ABS_MIN)
)
df = df[mask].copy()
df["ret_20d"]     = ret_20d.iloc[-1].reindex(df.index)
df["score"]       = df["hot_pct"] * df["accel"].clip(upper=3.0) * (1 + df["ret_5d"])
df = df.sort_values("score", ascending=False).head(TOP_N)
df["close_price"] = close.iloc[-1].reindex(df.index)
df["price_pos"]   = price_pos.reindex(df.index)
df["month_pos"]   = month_pos.reindex(df.index)

print(f"宇宙股數（電子類）：{len(base)} 檔　熱門入榜：{len(df)} 檔")

# ── 近5日加速比歷史（用於 sparkline）────────────────────────
def _accel_series(n):
    end_idx = -n if n > 0 else None
    recent  = turnover_raw.iloc[-(n+3):end_idx].sum()
    prior   = turnover_raw.iloc[-(n+6):-(n+3)].sum()
    return recent / prior.replace(0, np.nan)

accel_hist_df = pd.concat(
    [_accel_series(n) for n in range(4, -1, -1)], axis=1
)
accel_hist_df.columns = range(5)
accel_hist = {
    sid: accel_hist_df.loc[sid].tolist()
    for sid in df.index if sid in accel_hist_df.index
}

# ═══════════════════════════════════════════════════════════
#  歷史快照
# ═══════════════════════════════════════════════════════════
def save_snapshot(df, date_str):
    HISTORY_DIR.mkdir(exist_ok=True)
    snap = {}
    for theme, g in df.groupby("theme"):
        snap[theme] = {
            "count":      len(g),
            "avg_hot_pct": round(float(g["hot_pct"].mean()), 3),
            "avg_accel":  round(float(g["accel"].mean()), 3),
            "avg_ret_5d": round(float(g["ret_5d"].mean()), 4),
            "stocks":     list(g.index),
        }
    with open(HISTORY_DIR / f"{date_str}.json", "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=2)

def get_history_snapshots(today_str):
    files = sorted(HISTORY_DIR.glob("*.json")) if HISTORY_DIR.exists() else []
    dates = [f.stem for f in files if f.stem < today_str]
    if not dates:
        return None, None, None, None
    yday_date = dates[-1]
    week_cutoff = (datetime.strptime(today_str, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
    older = [d for d in dates if d <= week_cutoff]
    week_date = older[-1] if older else None
    def load(d):
        if d is None: return None
        p = HISTORY_DIR / f"{d}.json"
        return json.load(open(p, encoding="utf-8")) if p.exists() else None
    return load(yday_date), load(week_date), yday_date, week_date

save_snapshot(df, today_str)
hist_yday, hist_week, yday_label, week_label = get_history_snapshots(today_str)

# ═══════════════════════════════════════════════════════════
#  族群擴散表
# ═══════════════════════════════════════════════════════════
diffusion = df.groupby("theme").agg(
    hot_count    = ("score",    "count"),
    avg_ret      = ("ret_5d",   "mean"),
    avg_hot_pct  = ("hot_pct",  "mean"),
    avg_accel    = ("accel",    "mean"),
).copy()

diffusion = diffusion.join(theme_total).join(limit_up_by_theme)
diffusion["total"]     = diffusion["total"].fillna(0).astype(int)
diffusion["limit_up"]  = diffusion["limit_up"].fillna(0).astype(int)
diffusion["part_rate"] = diffusion["hot_count"] / diffusion["total"].replace(0, np.nan)

diffusion["yday_count"] = diffusion.index.map(
    lambda t: hist_yday[t]["count"] if hist_yday and t in hist_yday else np.nan)
diffusion["week_count"] = diffusion.index.map(
    lambda t: hist_week[t]["count"] if hist_week and t in hist_week else np.nan)
diffusion["trend_week"] = (diffusion["hot_count"] - diffusion["week_count"]).fillna(np.nan)

diffusion = diffusion.sort_values("avg_hot_pct", ascending=False)

today_themes = set(df["theme"].unique())
macro_status = {}
for macro, sub_set in MACRO_GROUPS.items():
    active = sorted(today_themes & sub_set)
    week_active = {t for t in sub_set if hist_week and t in hist_week} if hist_week else set()
    macro_status[macro] = {
        "active":            active,
        "inactive":          sorted(sub_set - today_themes),
        "active_count":      len(active),
        "total_count":       len(sub_set),
        "week_active_count": len(week_active),
        "new_vs_week":       len(active) - len(week_active),
    }

# ═══════════════════════════════════════════════════════════
#  自動評論
# ═══════════════════════════════════════════════════════════
def gen_comments(df, diffusion, macro_status):
    notes = []

    # ── 1. 宏觀族群擴散 ──────────────────────────────────────
    expanding = [(m, s) for m, s in macro_status.items()
                 if s["active_count"] >= 3 or s["new_vs_week"] >= 2]
    expanding.sort(key=lambda x: -x[1]["active_count"])
    if expanding:
        items = []
        for macro, s in expanding[:3]:
            trend = f"較上週+{s['new_vs_week']}" if s["new_vs_week"] > 0 else (
                    f"較上週{s['new_vs_week']}" if s["new_vs_week"] < 0 else "與上週相當")
            items.append(f"【{macro}】{s['active_count']}/{s['total_count']} 子主題（{trend}）："
                         f"{'、'.join(s['active'][:5])}")
        notes.append(("🌊 族群擴散",
            "\n  ".join(items) + "。真正大行情的特徵是橫向擴散持續擴大。"))

    # ── 2. 主力族群 ──────────────────────────────────────────
    top = diffusion.iloc[0]
    top_theme = diffusion.index[0]
    top_stocks = [f"{sid} {r['name']}" for sid, r in df[df["theme"] == top_theme].iterrows()]
    part_str  = f"，佔全體 {top['part_rate']:.0%}" if pd.notna(top["part_rate"]) else ""
    lim_str   = f"，漲停 {int(top['limit_up'])} 檔" if top["limit_up"] > 0 else ""
    trend_str = ""
    if pd.notna(top["week_count"]):
        delta = int(top["hot_count"] - top["week_count"])
        trend_str = f"，較上週{'↑'+str(delta) if delta>0 else ('↓'+str(abs(delta)) if delta<0 else '持平')}"
    notes.append(("📊 主力族群",
        f"【{top_theme}】熱門 {int(top['hot_count'])} 檔（共 {int(top['total'])} 檔{part_str}{lim_str}{trend_str}），"
        f"熱度百分位 {top['avg_hot_pct']:.0%}、加速比 {top['avg_accel']:.2f}x。"
        f"個股：{'、'.join(top_stocks)}。"))

    # ── 3. 入榜數擴張 ────────────────────────────────────────
    if hist_week:
        exp = diffusion[diffusion["trend_week"] >= 2].sort_values("trend_week", ascending=False)
        if not exp.empty:
            items = [f"【{t}】{int(r['week_count']) if pd.notna(r['week_count']) else 0}→{int(r['hot_count'])}檔（+{int(r['trend_week'])}）"
                     for t, r in exp.head(4).iterrows()]
            notes.append(("📈 入榜數擴張",
                f"以下族群本週入榜數較上週明顯增加：{'、'.join(items)}。"))

    # ── 4. 高參與率 ──────────────────────────────────────────
    high_part = diffusion[diffusion["part_rate"] >= 0.15].sort_values("part_rate", ascending=False)
    if not high_part.empty:
        items = [f"【{t}】{int(r['hot_count'])}/{int(r['total'])}檔（{r['part_rate']:.0%}）"
                 for t, r in high_part.head(4).iterrows()]
        notes.append(("🎯 高參與率",
            f"超過15%的股票同時入熱榜，族群性行情確立：{'、'.join(items)}。"))

    # ── 5. 黑馬個股 ─────────────────────────────────────────
    theme_cnt = df.groupby("theme").size()
    rare = df[df["theme"].isin(theme_cnt[theme_cnt == 1].index)].sort_values("score", ascending=False)
    if not rare.empty:
        items = [f"{sid} {r['name']}（{r['theme']}，5日{r['ret_5d']:+.0%}，加速{r['accel']:.2f}x）"
                 for sid, r in rare.head(4).iterrows()]
        notes.append(("💡 黑馬個股",
            f"單獨入榜、非主流主題，留意是否有特定題材驅動：{'、'.join(items)}。"))

    # ── 6. 爆量盤整 ─────────────────────────────────────────
    vol_flat = df[(df["hot_pct"] >= 0.90) & (df["ret_5d"].abs() < 0.04)].sort_values("hot_pct", ascending=False)
    if not vol_flat.empty:
        items = [f"{sid} {r['name']}（百分位{r['hot_pct']:.0%}，5日{r['ret_5d']:+.1%}）"
                 for sid, r in vol_flat.head(3).iterrows()]
        notes.append(("⚠️ 爆量盤整",
            f"量能處於歷史高位但股價幾乎沒動，留意高位換手或出貨：{'、'.join(items)}。"))

    return notes

comments = gen_comments(df, diffusion, macro_status)

# ── 終端機輸出 ────────────────────────────────────────────
print(f"\n{'─'*65}")
print("族群擴散概覽")
print(f"{'─'*65}")
print(f"{'族群':<12} {'入榜/全體':>8} {'參與率':>6} {'漲停':>4} {'上週':>5} {'趨勢':>5} {'熱度百分位':>9} {'加速比':>6}")
print(f"{'─'*65}")
for t, r in diffusion.iterrows():
    wk    = f"{int(r['week_count'])}" if pd.notna(r["week_count"]) else "-"
    trend = ""
    if pd.notna(r["trend_week"]):
        d = int(r["trend_week"])
        trend = f"+{d}" if d > 0 else (str(d) if d < 0 else "→")
    print(f"{t:<12} {int(r['hot_count']):>3}/{int(r['total']):<4} "
          f"{r['part_rate']:>5.0%}  {int(r['limit_up']):>3}  {wk:>5}  {trend:>5}  "
          f"{r['avg_hot_pct']:>8.0%}  {r['avg_accel']:>5.2f}x")

print(f"\n{'─'*65}")
print("熱門個股")
print(f"{'─'*65}")
print(f"{'代號':6} {'名稱':14} {'主題':12} {'成交價':>7} {'成交值':>8} {'放量位置':>7} {'月內位置':>7} {'1日':>6} {'5日':>7}")
print(f"{'─'*72}")
for sid, row in df.iterrows():
    tv   = f"{row['turnover']/1e8:.0f}億" if pd.notna(row["turnover"]) else "-"
    cp   = row.get("close_price", float("nan"))
    cp_str = f"{cp:.2f}" if pd.notna(cp) else "-"
    pp   = row.get("price_pos", float("nan"))
    pp_str = f"{pp:.0%}" if pd.notna(pp) else "-"
    mp   = row.get("month_pos", float("nan"))
    mp_str = f"{mp:.0%}" if pd.notna(mp) else "-"
    print(f"{sid:6} {row['name'][:12]:14} {row['theme']:12} {cp_str:>7} {tv:>8} "
          f"{pp_str:>6}  {mp_str:>6}  "
          f"{row['ret_1d']:>+6.1%} {row['ret_5d']:>+7.1%}")

for title, body in comments:
    print(f"\n{title}\n  {body}")

# ═══════════════════════════════════════════════════════════
#  TXT 輸出
# ═══════════════════════════════════════════════════════════
def export_txt(df, diffusion, macro_status, comments, date_str):
    lines = [
        "# 台股熱門電子股追蹤報表",
        f"日期：{date_str}",
        f"篩選：歷史熱度百分位≥{PERCENTILE_MIN:.0%}、加速比≥{ACCEL_MIN}、成交值≥{TURNOVER_ABS_MIN/1e8:.0f}億、市值≥{MARKET_CAP_MIN/1e8:.0f}億",
        f"熱門入榜：{len(df)} 檔　比較基準：昨日={yday_label or '無'}　上週={week_label or '無'}",
        "",
        "## 指標說明",
        f"- 放量位置：現價／三年高點，反映放量發生在歷史的哪個價位區間",
        "  <40% 低檔　40~80% 中性　>80% 偏高",
        "- 加速比：近3日換手率合計 ÷ 前3日換手率合計（>1.0=熱度仍在放大）",
        "- 參與率：熱門入榜數 ÷ 該主題上市上櫃總股數",
        "- 漲停：今日 ret_1d≥9.5% 的家數（含非熱門股）",
        "- 趨勢：較上週入榜數變化（+擴散、-收縮）",
        "",
        "## 宏觀族群擴散",
        "",
    ]
    for macro, s in macro_status.items():
        bar = "█" * s["active_count"] + "░" * (s["total_count"] - s["active_count"])
        trend = f"+{s['new_vs_week']}" if s["new_vs_week"] > 0 else str(s["new_vs_week"])
        lines.append(f"{macro}: {bar} {s['active_count']}/{s['total_count']} 子主題"
                     f"  較上週{trend}  入榜：{', '.join(s['active']) or '無'}")
    lines.append("")

    lines += ["## 族群擴散明細", ""]
    lines.append(f"{'族群':<12} {'入榜':>4} {'全體':>5} {'參與率':>6} {'漲停':>4} {'昨日':>5} {'上週':>5} {'趨勢':>5} {'熱度%位':>7} {'加速比':>7} {'5日均漲':>8}")
    lines.append("-" * 80)
    for t, r in diffusion.iterrows():
        yd    = f"{int(r['yday_count'])}" if pd.notna(r["yday_count"]) else "-"
        wk    = f"{int(r['week_count'])}" if pd.notna(r["week_count"]) else "-"
        trend = ""
        if pd.notna(r["trend_week"]):
            d = int(r["trend_week"])
            trend = f"+{d}" if d > 0 else (str(d) if d < 0 else "→")
        lines.append(
            f"{t:<12} {int(r['hot_count']):>4} {int(r['total']):>5} "
            f"{r['part_rate']:>5.0%}  {int(r['limit_up']):>3}  {yd:>5}  {wk:>5}  {trend:>5}  "
            f"{r['avg_hot_pct']:>6.0%}  {r['avg_accel']:>6.2f}x  {r['avg_ret']:>+7.1%}")
    lines.append("")

    lines += ["## 個股明細（依分數排序）", ""]
    lines.append(f"{'代號':<6} {'名稱':<12} {'族群':<12} {'今日成交價':>10} {'市值':>7} {'成交值':>7} {'放量位置':>7} {'月內位置':>7} {'1日':>6} {'5日':>7} {'20日':>7}")
    lines.append("-" * 103)
    for sid, row in df.iterrows():
        mc     = row["market_cap"]
        mc_str = (f"{mc/1e12:.1f}兆" if pd.notna(mc) and mc >= 1e12
                  else (f"{mc/1e8:.0f}億" if pd.notna(mc) else "-"))
        tv   = f"{row['turnover']/1e8:.0f}億" if pd.notna(row["turnover"]) else "-"
        cp   = row.get("close_price", float("nan"))
        cp_str = f"{cp:.2f}" if pd.notna(cp) else "-"
        pp   = row.get("price_pos", float("nan"))
        pp_str = f"{pp:.0%}" if pd.notna(pp) else "-"
        mp   = row.get("month_pos", float("nan"))
        mp_str = f"{mp:.0%}" if pd.notna(mp) else "-"
        r20  = row.get("ret_20d", float("nan"))
        lines.append(
            f"{sid:<6} {row['name'][:10]:<12} {row['theme']:<12} {cp_str:>10} {mc_str:>7} {tv:>7} "
            f"{pp_str:>6}  {mp_str:>6}  "
            f"{row['ret_1d']:>+6.1%} {row['ret_5d']:>+7.1%} {r20:>+7.1%}")
    lines.append("")

    lines += ["## 系統評論", ""]
    for title, body in comments:
        lines.append(f"### {title}")
        lines.append(body)
        lines.append("")

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"熱門股追蹤_{date_str}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\nTXT 已輸出：熱門股追蹤_{date_str}.txt")

export_txt(df, diffusion, macro_status, comments, today_str)

# ═══════════════════════════════════════════════════════════
#  HTML 輸出
# ═══════════════════════════════════════════════════════════
def pct_col(v):
    if pd.isna(v): return "#8b949e"
    if v >= 0.20:  return "#00e676"
    if v >= 0.08:  return "#69f0ae"
    if v >= 0.02:  return "#b9f6ca"
    if v >= 0:     return "#c8e6c9"
    if v >= -0.05: return "#ff8a80"
    return "#ff5252"

def price_pos_col(v):
    if pd.isna(v): return "#8b949e"
    if v < 0.40:   return "#00e676"   # 低檔啟動
    if v < 0.60:   return "#8b949e"   # 中性
    if v < 0.80:   return "#ffab40"   # 偏高留意
    return "#ff5252"                   # 高檔出貨風險

def price_pos_bar(v):
    if pd.isna(v): return "-"
    w = int(v * 100)
    c = price_pos_col(v)
    return (f'<div style="display:flex;align-items:center;gap:6px">'
            f'<div style="width:55px;background:#21262d;border-radius:3px;height:10px">'
            f'<div style="width:{w}%;background:{c};height:10px;border-radius:3px"></div></div>'
            f'<span style="color:{c};font-weight:600">{v:.0%}</span></div>')

def month_pos_col(v):
    if pd.isna(v): return "#8b949e"
    if v >= 0.80:  return "#00e676"   # 月內高位，動能強
    if v >= 0.60:  return "#69f0ae"
    if v >= 0.40:  return "#c9d1d9"   # 中性
    if v >= 0.20:  return "#ffab40"   # 偏低
    return "#ff5252"                   # 月內低位，偏弱

def month_pos_bar(v):
    if pd.isna(v): return "-"
    w = int(v * 100)
    c = month_pos_col(v)
    return (f'<div style="display:flex;align-items:center;gap:6px">'
            f'<div style="width:55px;background:#21262d;border-radius:3px;height:10px">'
            f'<div style="width:{w}%;background:{c};height:10px;border-radius:3px"></div></div>'
            f'<span style="color:{c};font-weight:600">{v:.0%}</span></div>')

def accel_col(v):
    if pd.isna(v): return "#8b949e"
    if v >= 1.5:  return "#00e676"
    if v >= 1.2:  return "#69f0ae"
    if v >= 0.9:  return "#c9d1d9"
    if v >= 0.75: return "#ff8a80"
    return "#ff5252"

def accel_sparkline(values):
    cur   = values[-1] if values else float("nan")
    cur_c = accel_col(cur)
    cur_s = f"{cur:.2f}x" if pd.notna(cur) else "-"
    valid = [(i, v) for i, v in enumerate(values) if pd.notna(v) and v > 0]
    if len(valid) < 2:
        return f'<span style="color:{cur_c};font-weight:600">{cur_s}</span>'
    vs   = [v for _, v in valid]
    vmin = min(vs) * 0.95
    vmax = max(vs) * 1.05
    rng  = vmax - vmin if vmax != vmin else 0.2
    W, H = 52, 20
    pts  = [(i / (len(values)-1) * W, H - (v-vmin)/rng*(H-4) - 2) for i, v in valid]
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    lx, ly = pts[-1]
    last2  = [v for _, v in valid[-2:]]
    diff   = last2[-1] - last2[0]
    lc = "#00e676" if diff > 0.05 else ("#ff5252" if diff < -0.05 else "#8b949e")
    return (f'<div style="display:flex;align-items:center;gap:6px">'
            f'<svg width="{W}" height="{H}" style="overflow:visible;vertical-align:middle">'
            f'<polyline points="{poly}" fill="none" stroke="{lc}" '
            f'stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/>'
            f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="2.8" fill="{lc}"/>'
            f'</svg>'
            f'<span style="color:{cur_c};font-weight:600;font-size:0.82rem">{cur_s}</span>'
            f'</div>')

THEME_COLOR = {
    "晶圓代工":  "#1565c0", "IC設計":    "#1976d2", "封裝測試":  "#0288d1",
    "矽晶圓":   "#0d47a1", "功率半導體": "#283593", "記憶體":    "#01579b",
    "記憶體模組":"#0277bd", "PCB/載板":  "#1a237e",
    "伺服器/AI": "#880e4f", "散熱":      "#ad1457", "電源":      "#c62828",
    "EMS/代工":  "#b71c1c", "連接器":    "#6a1b9a",
    "網通":      "#00695c", "電腦週邊":  "#2e7d32",
    "面板":      "#e65100", "光電/LED":  "#f57f17", "光電":      "#ff6f00",
    "被動元件":  "#4e342e", "品牌PC/NB": "#37474f", "電子通路":  "#455a64",
    "半導體":    "#1b5e20", "電子零組件":"#33691e", "其他電子":  "#424242",
    "電機":      "#4a148c", "資訊服務":  "#006064", "數位雲端":  "#1565c0",
    "汽車電子":  "#bf360c",
}
DEFAULT_COLOR = "#21262d"

def theme_badge(t):
    bg = THEME_COLOR.get(t, DEFAULT_COLOR)
    return (f'<span style="background:{bg};color:white;padding:2px 8px;'
            f'border-radius:10px;font-size:0.78rem;white-space:nowrap">{t}</span>')

# ── 宏觀擴散橫幅 ─────────────────────────────────────────
macro_bars_html = []
for macro, s in sorted(macro_status.items(), key=lambda x: x[1]["active_count"], reverse=True):
    pct   = s["active_count"] / s["total_count"] if s["total_count"] else 0
    color = "#00e676" if pct >= 0.6 else ("#ffab40" if pct >= 0.35 else "#484f58")
    trend_txt = f"+{s['new_vs_week']}" if s["new_vs_week"] > 0 else (str(s["new_vs_week"]) if s["new_vs_week"] < 0 else "→")
    badges = " ".join(f'<span style="font-size:0.75rem;background:#30363d;padding:1px 5px;border-radius:4px">{t}</span>' for t in s["active"])
    macro_bars_html.append(f"""
    <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px 16px;min-width:200px;flex:1">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
        <span style="font-weight:700;font-size:0.88rem">{macro}</span>
        <span style="color:{color};font-size:0.82rem">{s['active_count']}/{s['total_count']} 子主題
          <span style="color:#8b949e;font-size:0.78rem">（{trend_txt} vs 上週）</span>
        </span>
      </div>
      <div style="background:#21262d;border-radius:3px;height:8px;margin-bottom:8px">
        <div style="width:{int(pct*100)}%;background:{color};height:8px;border-radius:3px"></div>
      </div>
      <div style="display:flex;flex-wrap:wrap;gap:4px">{badges or '<span style="color:#484f58;font-size:0.78rem">今日無入榜</span>'}</div>
    </div>""")

# ── 族群擴散卡片 ─────────────────────────────────────────
diff_cards_html = []
theme_all_stocks = {
    theme: [
        (sid, f"{sid} {row['name']}")
        for sid, row in g.sort_index().iterrows()
    ]
    for theme, g in base.groupby("theme")
}
hot_stock_ids = set(df.index)
for t, r in diffusion.sort_values("part_rate", ascending=False).iterrows():
    if pd.isna(r["part_rate"]) or r["part_rate"] <= 0.02:
        continue
    bg       = THEME_COLOR.get(t, DEFAULT_COLOR)
    aclr     = accel_col(r["avg_accel"])
    trend_d  = int(r["trend_week"]) if pd.notna(r["trend_week"]) else None
    trend_html = ""
    if trend_d is not None:
        tc = "#00e676" if trend_d > 0 else ("#ff5252" if trend_d < 0 else "#8b949e")
        trend_html = f'<span style="color:{tc};font-size:0.75rem">vs上週{"+"+str(trend_d) if trend_d>0 else str(trend_d)}</span>'
    lim_html = f'<span style="color:#ff3d00;font-size:0.75rem"> 漲停{int(r["limit_up"])}</span>' if r["limit_up"] > 0 else ""
    tooltip_html = ""
    card_class = "diff-card"
    if r["part_rate"] > 0.19:
        stocks = theme_all_stocks.get(t, [])
        stocks_html = "".join(
            f'<li class="{"is-hot" if sid in hot_stock_ids else ""}">{escape(label)}</li>'
            for sid, label in stocks
        )
        tooltip_html = (
            f'<div class="diff-tooltip">'
            f'<div class="diff-tooltip-title">{escape(str(t))} 全族群股票（{len(stocks)}檔）</div>'
            f'<ul>{stocks_html}</ul>'
            f'</div>'
        )
        card_class += " has-tooltip"
    diff_cards_html.append(
        f'<div class="{card_class}" style="background:{bg}">'
        f'<div style="color:rgba(255,255,255,0.7);font-size:0.78rem">{escape(str(t))}</div>'
        f'<div style="color:white;font-weight:700;font-size:1.05rem;margin:3px 0">'
        f'{int(r["hot_count"])}/{int(r["total"])} 檔 '
        f'<span style="font-size:0.78rem;font-weight:400">({r["part_rate"]:.0%})</span>'
        f'{lim_html}</div>'
        f'<div style="color:rgba(255,255,255,0.85);font-size:0.8rem">'
        f'熱度 {r["avg_hot_pct"]:.0%} &nbsp;'
        f'<span style="color:{aclr}">加速{r["avg_accel"]:.2f}x</span> &nbsp;'
        f'{trend_html}</div>{tooltip_html}</div>')

# ── 個股表格 ─────────────────────────────────────────────
theme_order = [
    "晶圓代工","矽晶圓","IC設計","功率半導體","記憶體","記憶體模組",
    "封裝測試","PCB/載板","被動元件","散熱","伺服器/AI","EMS/代工",
    "電源","網通","連接器","面板","光電/LED","品牌PC/NB","電子通路",
    "半導體","電子零組件","光電","電腦週邊","其他電子","電機",
    "資訊服務","數位雲端","汽車電子",
]
df["theme_order"] = df["theme"].map({t: i for i, t in enumerate(theme_order)}).fillna(99)
df_sorted = df.sort_values(["theme_order","score"], ascending=[True, False])

rows_html  = []
prev_theme = None
for sid, row in df_sorted.iterrows():
    tv  = f"{row['turnover']/1e8:.0f}億" if pd.notna(row["turnover"]) else "-"
    sep = '<tr style="height:6px"><td colspan="12"></td></tr>' if row["theme"] != prev_theme else ""
    prev_theme = row["theme"]
    mc     = row["market_cap"]
    mc_str = (f"{mc/1e12:.1f}兆" if pd.notna(mc) and mc >= 1e12 else (f"{mc/1e8:.0f}億" if pd.notna(mc) else "-"))
    cp     = row.get("close_price", float("nan"))
    cp_str = f"{cp:.2f}" if pd.notna(cp) else "-"
    r20    = row.get("ret_20d", float("nan"))
    name_js = row['name'].replace("'", "").replace('"', "")
    rows_html.append(f"""{sep}<tr>
      <td style="font-weight:700;color:#58a6ff;cursor:pointer;text-decoration:underline dotted"
          onclick="openChart('{sid}','{name_js}')" title="點擊查看 {name_js} K線圖">{sid}</td>
      <td>{row['name']}</td>
      <td>{theme_badge(row['theme'])}</td>
      <td style="text-align:right;color:{pct_col(row['ret_1d'])};font-weight:600">{cp_str}</td>
      <td style="text-align:right;color:#8b949e">{mc_str}</td>
      <td style="text-align:right;color:#58a6ff">{tv}</td>
      <td>{price_pos_bar(row['price_pos'])}</td>
      <td>{month_pos_bar(row['month_pos'])}</td>
      <td>{accel_sparkline(accel_hist.get(sid, [float('nan')]*5))}</td>
      <td style="text-align:right;color:{pct_col(row['ret_1d'])};font-weight:600">{row['ret_1d']:+.1%}</td>
      <td style="text-align:right;color:{pct_col(row['ret_5d'])};font-weight:600">{row['ret_5d']:+.1%}</td>
      <td style="text-align:right;color:{pct_col(r20)};font-weight:600">{r20:+.1%}</td>
    </tr>""")

open_chart_js = f"""
const embeddedTWSECodes = new Set({twse_codes_json});
function openChart(sid, name) {{
    var code = String(sid);
    var ex = embeddedTWSECodes.size === 0 ? 'TWSE' : (embeddedTWSECodes.has(code) ? 'TWSE' : 'TPEX');
    var url = 'https://www.tradingview.com/chart/?symbol=' + ex + ':' + code;
    window.open(url, 'kline_' + sid,
        'width=1280,height=800,resizable=yes,toolbar=no,location=yes,menubar=no,status=no');
}}
"""

def build_comments_html(comments):
    out = []
    for icon_title, body in comments:
        parts = icon_title.split(" ", 1)
        icon, title = parts[0], (parts[1] if len(parts) > 1 else icon_title)
        out.append(f'<div class="note"><div class="note-title">{icon} {title}</div>'
                   f'<div class="note-body">{body.replace(chr(10), "<br>")}</div></div>')
    return "\n".join(out)

html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<title>熱門股追蹤 {today_str}</title>
<style>
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ background:#0d1117; color:#e6edf3; font-family:'Segoe UI','Microsoft JhengHei',sans-serif; padding:20px 28px; }}
h1 {{ font-size:1.4rem; color:#58a6ff; }}
h2 {{ color:#8b949e; margin:24px 0 10px; letter-spacing:.04em; text-transform:uppercase; font-size:0.78rem; }}
.sub {{ color:#8b949e; font-size:0.86rem; margin:4px 0 20px; line-height:1.8; }}
.macro-row {{ display:flex; flex-wrap:wrap; gap:10px; margin-bottom:20px; }}
.cards {{ display:flex; flex-wrap:wrap; gap:10px; margin-bottom:24px; }}
.diff-card {{ position:relative; border-radius:8px; padding:10px 14px; min-width:130px; }}
.diff-card.has-tooltip {{ cursor:help; }}
.diff-card.has-tooltip:hover {{ filter:brightness(1.08); z-index:5; }}
.diff-tooltip {{
  display:none; position:absolute; left:0; top:calc(100% + 8px); min-width:240px; max-width:360px;
  background:#161b22; border:1px solid #30363d; border-radius:8px; padding:10px 12px;
  box-shadow:0 12px 32px rgba(0,0,0,.38); color:#e6edf3; max-height:360px; overflow:auto;
}}
.diff-card.has-tooltip:hover .diff-tooltip {{ display:block; }}
.diff-tooltip-title {{ font-weight:700; font-size:0.82rem; margin-bottom:6px; color:#58a6ff; }}
.diff-tooltip ul {{ list-style:none; display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr)); gap:4px 10px; }}
.diff-tooltip li {{ font-size:0.78rem; line-height:1.45; color:#c9d1d9; white-space:nowrap; padding:2px 5px; border-left:2px solid transparent; border-radius:4px; }}
.diff-tooltip li.is-hot {{ color:#fff; background:rgba(255,171,64,.18); border-left-color:#ffab40; font-weight:700; }}
.notes-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(320px,1fr)); gap:10px; margin-bottom:28px; }}
.note {{ background:#161b22; border:1px solid #30363d; border-radius:8px; padding:14px 16px; }}
.note-title {{ font-weight:700; font-size:0.9rem; color:#e6edf3; margin-bottom:7px; }}
.note-body {{ font-size:0.84rem; color:#8b949e; line-height:1.8; }}
table {{ width:100%; border-collapse:collapse; font-size:0.88rem; }}
th {{ background:#161b22; color:#8b949e; padding:9px 12px; text-align:left; position:sticky; top:0; border-bottom:1px solid #30363d; white-space:nowrap; }}
td {{ padding:7px 12px; border-bottom:1px solid #1c2128; white-space:nowrap; }}
tr:hover td {{ background:#1c2128; }}
.footer {{ margin-top:32px; color:#484f58; font-size:0.78rem; text-align:center; line-height:1.8; }}
input#search {{ background:#161b22; border:1px solid #30363d; border-radius:6px; padding:7px 12px; color:#e6edf3; font-size:0.9rem; width:240px; margin-bottom:14px; }}
input#search::placeholder {{ color:#484f58; }}
</style>
</head>
<body>
<h1>熱門股追蹤表</h1>
<div class="sub">
  {latest_date.strftime('%Y年%m月%d日')} &nbsp;|&nbsp;
  歷史熱度百分位 &ge; {PERCENTILE_MIN:.0%} &nbsp;|&nbsp;
  加速比 &ge; {ACCEL_MIN} &nbsp;|&nbsp;
  成交值 &ge; {TURNOVER_ABS_MIN/1e8:.0f}億 &nbsp;|&nbsp;
  市值 &ge; {MARKET_CAP_MIN/1e8:.0f}億 &nbsp;|&nbsp;
  入榜 {len(df)} 檔<br>
  <span style="color:#484f58;font-size:0.78rem">
  比較基準：昨日={yday_label or '無'}　上週={week_label or '無'}
  熱度百分位 = 近3日量在過去{N_HIST}日（約1年）中的排名
  </span>
</div>

<h2>宏觀族群擴散</h2>
<div class="macro-row">{''.join(macro_bars_html)}</div>

<h2>子主題入榜（入榜數 / 全體　參與率）</h2>
<div class="cards">{''.join(diff_cards_html)}</div>

<h2>訊號評論</h2>
<div class="notes-grid">{build_comments_html(comments)}</div>

<input type="text" id="search" placeholder="搜尋代號 / 名稱 / 主題...">
<h2>個股明細</h2>
<table id="tbl">
  <thead><tr>
    <th>代號</th><th>名稱</th><th>主題</th>
    <th style="text-align:right">今日成交價</th>
    <th style="text-align:right">市值</th>
    <th style="text-align:right">成交值</th>
    <th>放量位置<br><small style="font-weight:400;color:#8b949e">現價／三年高點</small></th>
    <th>現在位置<br><small style="font-weight:400;color:#8b949e">現價／月內區間</small></th>
    <th>加速比趨勢（5日）</th>
    <th style="text-align:right">1日</th>
    <th style="text-align:right">5日</th>
    <th style="text-align:right">20日</th>
  </tr></thead>
  <tbody id="tbody">{''.join(rows_html)}</tbody>
</table>

<div class="footer">
  放量位置 = 現價／三年高點：&lt;40% 低檔　40~80% 中性　&gt;80% 偏高<br>
  參與率 = 熱門入榜/主題全體股數　主題分類見 theme_map.py
</div>

<script>
{open_chart_js}
document.getElementById('search').addEventListener('input', function() {{
  var q = this.value.toLowerCase();
  document.querySelectorAll('#tbody tr').forEach(function(tr) {{
    if (tr.children.length < 3) {{ tr.style.display=''; return; }}
    tr.style.display = tr.innerText.toLowerCase().includes(q) ? '' : 'none';
  }});
}});
</script>
</body>
</html>"""

out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"熱門股追蹤_{today_str}.html")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(html)
print(f"HTML 已輸出：{out_path}")
webbrowser.open(f"file:///{out_path.replace(chr(92), '/')}")
