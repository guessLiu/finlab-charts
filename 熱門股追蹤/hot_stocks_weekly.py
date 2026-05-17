"""
熱門股週報生成器 v2
- 深藍底色，明亮柔和色系
- 右欄 480px，代號+股名正確、字體更大
- 底部股票表與 hot_stocks 同欄位 + 可排序表頭
- 第一欄：代號 名稱 [族群badge]，點選開 K 線圖
"""
from dotenv import load_dotenv
load_dotenv()

import io, json, math, os, re, sys
import numpy as np
import pandas as pd
from datetime import date, timedelta
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).parent
REPORT_DIR = BASE_DIR / "reports"
SNAPSHOT_DIR = REPORT_DIR / "snapshots"

sys.path.insert(0, str(BASE_DIR))
from theme_map import THEME

N_HIST = 252
PERCENTILE_MIN   = 0.75
ACCEL_MIN        = 0.75
RET_5D_MIN       = 0.0
MARKET_CAP_MIN   = 30e8
TURNOVER_ABS_MIN = 30e8
TOP_N            = 20

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

MACRO_GROUPS = {
    "半導體供應鏈": {"晶圓代工","IC設計","封裝測試","矽晶圓","功率半導體","記憶體","記憶體模組","PCB/載板"},
    "AI/伺服器鏈":  {"伺服器/AI","散熱","電源","EMS/代工","連接器"},
    "網通/通訊鏈":  {"網通","連接器","電腦週邊"},
    "面板/光電鏈":  {"面板","光電/LED","光電"},
}
MACRO_COLORS = {
    "半導體供應鏈": "#9b8fd3",
    "AI/伺服器鏈":  "#56a7d8",
    "網通/通訊鏈":  "#6fcf97",
    "面板/光電鏈":  "#f2c94c",
    "其他":         "#74808c",
}
THEME_COLOR = {
    "晶圓代工":  "#5f86d6","IC設計":    "#6d8fd8","封裝測試":  "#56a7d8",
    "矽晶圓":   "#4d75c6","功率半導體": "#6387d3","記憶體":    "#527bd0",
    "記憶體模組":"#6387d3","PCB/載板":  "#4869a8",
    "伺服器/AI": "#4299b4","散熱":      "#4eaec3","電源":      "#56bfd0",
    "EMS/代工":  "#4299b4","連接器":    "#8d83d2",
    "網通":      "#5db98d","電腦週邊":  "#6fcf97",
    "面板":      "#c99a4e","光電/LED":  "#b89149","光電":      "#d4a04e",
    "被動元件":  "#8f8980","品牌PC/NB": "#74808c","電子通路":  "#65717e",
    "半導體":    "#69bd7d","電子零組件":"#8fbd60","其他電子":  "#74808c",
    "電機":      "#9b8fd3","資訊服務":  "#58aaa0","數位雲端":  "#6387d3",
    "汽車電子":  "#d68a55",
}

# ─────────────────────────────────────────────────────────────────
#  週期工具
# ─────────────────────────────────────────────────────────────────

def get_week_dates(end: date) -> list[date]:
    if end.weekday() >= 5:
        end -= timedelta(days=end.weekday() - 4)
    monday = end - timedelta(days=end.weekday())
    return [monday + timedelta(days=i) for i in range(5)]


def _week_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _auto_week_dates_from_finlab() -> list[date]:
    """Pick the latest finished report week from FinLab's available dates."""
    from finlab import data as fdata

    close = fdata.get("price:收盤價")
    if pd.Timestamp(close.index[-1]).date() < _prev_weekday():
        fdata.force_cloud_download = True
        close = fdata.get("price:收盤價")
        fdata.force_cloud_download = False

    available_dates = sorted(pd.to_datetime(close.index).date)
    latest = available_dates[-1]
    today = date.today()

    latest_monday = _week_monday(latest)
    latest_friday = latest_monday + timedelta(days=4)

    if latest.weekday() == 4 or today >= latest_friday:
        end = latest
    else:
        previous = [d for d in available_dates if d < latest_monday]
        if not previous:
            end = latest
        else:
            end = previous[-1]

    return get_week_dates(end)


def _prev_weekday() -> date:
    d = date.today() - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def build_week_data_from_finlab(dates: list[date]) -> dict:
    from finlab import data as fdata

    print("  載入 FinLab price:收盤價...")
    close = fdata.get("price:收盤價")

    if pd.Timestamp(close.index[-1]).date() < _prev_weekday():
        print("  本地資料過期，強制從雲端更新...")
        fdata.force_cloud_download = True
        close = fdata.get("price:收盤價")

    print("  載入 FinLab price:成交金額...")
    turnover_raw = fdata.get("price:成交金額")
    print("  載入 FinLab etl:market_value...")
    market_value = fdata.get("etl:market_value")
    print("  載入 FinLab company_basic_info...")
    company_info = fdata.get("company_basic_info")
    fdata.force_cloud_download = False

    close = pd.DataFrame(close)
    turnover_raw = pd.DataFrame(turnover_raw)
    market_value = pd.DataFrame(market_value)
    close.index = pd.to_datetime(close.index)
    turnover_raw.index = pd.to_datetime(turnover_raw.index)
    market_value.index = pd.to_datetime(market_value.index)
    turnover_raw = turnover_raw.reindex(close.index)
    market_value = market_value.reindex(close.index).ffill()

    ret_1d = close.pct_change(1, fill_method=None)
    ret_5d = close.pct_change(5, fill_method=None)
    turnover_rate = turnover_raw.div(market_value)
    turn_rate_3d_rolling = turnover_rate.rolling(3, min_periods=2).sum()

    company_by_id = company_info.set_index("stock_id")
    broad_cat = company_by_id[company_info.columns[3]]

    def map_theme(sid: str) -> str:
        t = THEME.get(sid, "")
        if not t:
            b = broad_cat.get(sid, "")
            t = BROAD_MAP.get(b, b)
        return t

    result = {}
    available = {ts.date(): i for i, ts in enumerate(close.index)}
    for d in dates:
        pos = available.get(d)
        if pos is None:
            continue
        if pos < max(6, N_HIST // 4):
            continue

        hist_start = max(0, pos - N_HIST + 1)
        hist_window = turn_rate_3d_rolling.iloc[hist_start:pos + 1]
        hot_pct = hist_window.rank(pct=True).iloc[-1]
        turn_3d_sum = turnover_rate.iloc[pos - 2:pos + 1].sum()
        turn_prev_sum = turnover_rate.iloc[pos - 5:pos - 2].sum()
        accel = turn_3d_sum / turn_prev_sum.replace(0, np.nan)

        base = pd.DataFrame({
            "ret_1d": ret_1d.iloc[pos],
            "ret_5d": ret_5d.iloc[pos],
            "hot_pct": hot_pct,
            "accel": accel,
            "turnover": turnover_raw.iloc[pos],
            "market_cap": market_value.iloc[pos],
        }).dropna(subset=["ret_1d", "ret_5d", "hot_pct", "accel"])

        base.index = base.index.astype(str)
        base = base[~base.index.str.startswith("0")]
        base = base[base.index.str.len() == 4]
        base["theme"] = base.index.map(map_theme)
        base = base[base["theme"].isin(KEEP_THEMES)]

        df = base[base["market_cap"].fillna(0) >= MARKET_CAP_MIN].copy()
        mask = (
            (df["hot_pct"] >= PERCENTILE_MIN) &
            (df["accel"] >= ACCEL_MIN) &
            (df["ret_5d"] >= RET_5D_MIN) &
            (df["turnover"].fillna(0) >= TURNOVER_ABS_MIN)
        )
        df = df[mask].copy()
        df["score"] = df["hot_pct"] * df["accel"].clip(upper=3.0) * (1 + df["ret_5d"])
        df = df.sort_values("score", ascending=False).head(TOP_N)

        snap = {}
        for theme, g in df.groupby("theme"):
            snap[theme] = {
                "count": len(g),
                "avg_hot_pct": round(float(g["hot_pct"].mean()), 3),
                "avg_accel": round(float(g["accel"].mean()), 3),
                "avg_ret_5d": round(float(g["ret_5d"].mean()), 4),
                "stocks": list(g.index),
            }
        result[d] = snap

    return result


def aggregate(week_data: dict) -> tuple[dict, list[date]]:
    dates = sorted(week_data.keys())
    themes: dict[str, dict] = {}

    for d in dates:
        for theme, info in week_data[d].items():
            if theme not in themes:
                themes[theme] = {
                    "days": [], "counts": {}, "hot_pcts": {},
                    "accels": {}, "rets": {}, "stock_days": {},
                }
            t = themes[theme]
            t["days"].append(d)
            t["counts"][d]   = info["count"]
            t["hot_pcts"][d] = info["avg_hot_pct"]
            t["accels"][d]   = info.get("avg_accel", 1.0)
            t["rets"][d]     = info.get("avg_ret_5d", 0.0)
            for sid in info["stocks"]:
                t["stock_days"][sid] = t["stock_days"].get(sid, 0) + 1

    n_total = len(dates)
    for theme, t in themes.items():
        n = len(t["days"])
        counts   = list(t["counts"].values())
        hot_pcts = list(t["hot_pcts"].values())
        accels   = list(t["accels"].values())

        t["n_days"]    = n
        t["n_total"]   = n_total
        t["avg_count"] = round(sum(counts) / n, 1)
        t["peak_count"]= max(counts)
        t["avg_hot"]   = round(sum(hot_pcts) / n, 3)
        t["avg_accel"] = round(sum(accels) / n, 2)
        t["avg_ret"]   = round(sum(list(t["rets"].values())) / n, 4)

        min_days = 1 if n_total <= 2 else 2
        t["core"] = sorted(
            [s for s, d in t["stock_days"].items() if d >= min_days],
            key=lambda s: -t["stock_days"][s],
        )
        t["all_stocks"] = sorted(t["stock_days"].keys())
        t["score"] = n * t["avg_count"] * t["avg_hot"]

        sdays = sorted(t["counts"])
        if len(sdays) >= 2:
            delta = t["counts"][sdays[-1]] - t["counts"][sdays[0]]
            t["trend"] = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
        else:
            t["trend"] = "—"

        t["macro"] = next(
            (g for g, ms in MACRO_GROUPS.items() if theme in ms), "其他"
        )

    return themes, dates


# ─────────────────────────────────────────────────────────────────
#  FinLab 資料載入
# ─────────────────────────────────────────────────────────────────

def load_finlab_data(all_stock_ids: set) -> dict:
    """載入每股指標，回傳 dict，失敗時回傳空 dict"""
    try:
        from finlab import data as fdata
        print("  載入 price:收盤價...")
        close        = fdata.get("price:收盤價")
        print("  載入 price:成交金額...")
        turnover_raw = fdata.get("price:成交金額")
        print("  載入 etl:market_value...")
        market_value = fdata.get("etl:market_value")
        print("  載入 company_basic_info...")
        company_info = fdata.get("company_basic_info")

        stock_name = (
            company_info.set_index("stock_id")[company_info.columns[2]]
            .str.replace(r"股份有限公司|有限公司", "", regex=True).str.strip()
        )

        ret_1d  = close.pct_change(1,  fill_method=None).iloc[-1]
        ret_5d  = close.pct_change(5,  fill_method=None).iloc[-1]
        ret_20d = close.pct_change(20, fill_method=None).iloc[-1]

        price_3yh = close.iloc[-756:].max()
        price_pos = (close.iloc[-1] / price_3yh).clip(upper=1.0)

        m_low    = close.iloc[-21:].min()
        m_high   = close.iloc[-21:].max()
        month_pos = ((close.iloc[-1] - m_low) / (m_high - m_low).replace(0, np.nan)).clip(0, 1)

        # 5-day accel sparkline
        def _accel(n):
            end_idx = -n if n > 0 else None
            recent  = turnover_raw.iloc[-(n+3):end_idx].sum()
            prior   = turnover_raw.iloc[-(n+6):-(n+3)].sum()
            return recent / prior.replace(0, np.nan)

        accel_hist_df = pd.concat([_accel(n) for n in range(4, -1, -1)], axis=1)
        accel_hist_df.columns = range(5)

        metrics = {}
        for sid in all_stock_ids:
            metrics[sid] = {
                "name":      stock_name.get(sid, ""),
                "close":     close.iloc[-1].get(sid, float("nan")),
                "market_cap":market_value.iloc[-1].get(sid, float("nan")),
                "turnover":  turnover_raw.iloc[-1].get(sid, float("nan")),
                "ret_1d":    ret_1d.get(sid, float("nan")),
                "ret_5d":    ret_5d.get(sid, float("nan")),
                "ret_20d":   ret_20d.get(sid, float("nan")),
                "price_pos": price_pos.get(sid, float("nan")),
                "month_pos": month_pos.get(sid, float("nan")),
                "accel_hist":(accel_hist_df.loc[sid].tolist()
                              if sid in accel_hist_df.index else [float("nan")] * 5),
            }

        # TWSE codes — 市場別欄值為 'sii'(上市) / 'otc'(上櫃)
        twse_codes: set = set()
        try:
            ci = company_info.set_index("stock_id")
            for col in ci.columns:
                vals = ci[col].astype(str).str.strip()
                if (vals == 'sii').any() and (vals == 'otc').any():
                    twse_codes = set(ci.index[vals == 'sii'])
                    break
        except Exception:
            pass

        return {"metrics": metrics, "twse_codes": twse_codes, "ok": True}

    except Exception as e:
        print(f"  [WARN] FinLab 資料載入失敗：{e}，部分欄位將顯示 -")
        return {"metrics": {}, "twse_codes": set(), "ok": False}


# ─────────────────────────────────────────────────────────────────
#  HTML 輔助函式
# ─────────────────────────────────────────────────────────────────

def heat_color(pct: float) -> str:
    if pct >= 0.92: return "#d6a85b"
    if pct >= 0.82: return "#b99a65"
    if pct >= 0.72: return "#9a8f72"
    return "#74808c"


def ret_color(v: float) -> str:
    if math.isnan(v): return "#74808c"
    return "#6fcf97" if v >= 0 else "#eb5757"


def accel_col(v) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)): return "#74808c"
    if v >= 1.5:  return "#6fcf97"
    if v >= 1.2:  return "#8fd9ad"
    if v >= 0.9:  return "#8792a0"
    if v >= 0.75: return "#df8a8a"
    return "#eb5757"


def pos_bar(v: float, colors: tuple = ("#6fcf97", "#f2c94c", "#eb5757")) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return '<span style="color:#56616d">—</span>'
    pct = int(v * 100)
    c = colors[0] if v >= 0.6 else (colors[1] if v >= 0.3 else colors[2])
    return (
        f'<div style="display:flex;align-items:center;gap:5px">'
        f'<div style="width:48px;background:#2b3540;border-radius:3px;height:7px">'
        f'<div style="width:{pct}%;background:{c};height:7px;border-radius:3px"></div></div>'
        f'<span style="color:{c};font-size:13px;font-weight:600">{pct}%</span></div>'
    )


def sparkline(values) -> str:
    cur   = values[-1] if values else float("nan")
    cur_c = accel_col(cur)
    cur_s = f"{cur:.2f}×" if not (isinstance(cur, float) and math.isnan(cur)) else "—"
    valid = [(i, v) for i, v in enumerate(values) if not (isinstance(v, float) and math.isnan(v)) and v > 0]
    if len(valid) < 2:
        return f'<span style="color:{cur_c};font-weight:600">{cur_s}</span>'
    vs   = [v for _, v in valid]
    vmin, vmax = min(vs) * 0.95, max(vs) * 1.05
    rng  = vmax - vmin if vmax != vmin else 0.2
    W, H = 52, 20
    pts  = [(i / (len(values) - 1) * W, H - (v - vmin) / rng * (H - 4) - 2) for i, v in valid]
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    lx, ly = pts[-1]
    diff   = valid[-1][1] - valid[-2][1] if len(valid) >= 2 else 0
    lc     = "#6fcf97" if diff > 0.05 else ("#eb5757" if diff < -0.05 else "#74808c")
    return (
        f'<div style="display:flex;align-items:center;gap:5px">'
        f'<svg width="{W}" height="{H}" style="overflow:visible;vertical-align:middle">'
        f'<polyline points="{poly}" fill="none" stroke="{lc}" stroke-width="1.8" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="2.8" fill="{lc}"/></svg>'
        f'<span style="color:{cur_c};font-weight:600;font-size:11px">{cur_s}</span></div>'
    )


def fmt_mc(v) -> str:
    if isinstance(v, float) and math.isnan(v): return "—"
    if v >= 1e12: return f"{v/1e12:.1f}兆"
    return f"{v/1e8:.0f}億"


def fmt_num(v, suffix="億", divisor=1e8, fmt=".0f") -> str:
    if isinstance(v, float) and math.isnan(v): return "—"
    return f"{v/divisor:{fmt}}{suffix}"


# ─────────────────────────────────────────────────────────────────
#  Snapshot（跨週延續率）
# ─────────────────────────────────────────────────────────────────

def save_snapshot(themes: dict, report_date: date) -> None:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    snap = {theme: t["avg_count"] for theme, t in themes.items()}
    (SNAPSHOT_DIR / f"{report_date}.json").write_text(
        json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8"
    )

def load_last_snapshot(before_date: date) -> dict:
    if not SNAPSHOT_DIR.exists():
        return {}
    for f in sorted(SNAPSHOT_DIR.glob("*.json"), reverse=True):
        try:
            if date.fromisoformat(f.stem) < before_date:
                return json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
    return {}

# ─────────────────────────────────────────────────────────────────
#  HTML 渲染
# ─────────────────────────────────────────────────────────────────

def render_html(
    themes: dict,
    week_dates: list[date],
    loaded_dates: list[date],
    finlab: dict,
    week_label: str,
    last_snap: dict | None = None,
) -> str:

    metrics   = finlab["metrics"]
    twse_codes= finlab["twse_codes"]
    DAY_LABELS= ["週一","週二","週三","週四","週五"]
    sorted_themes = sorted(themes.items(), key=lambda x: -x[1]["score"])
    n_avail   = len(loaded_dates)

    def tv_url(sid: str) -> str:
        exch = ("TWSE" if twse_codes and sid in twse_codes else
                ("TWSE" if not twse_codes and len(sid) == 4 else "TPEX"))
        return f"https://www.tradingview.com/chart/?symbol={exch}:{sid}"

    def theme_badge(t: str) -> str:
        bg = THEME_COLOR.get(t, "#65717e")
        return (f'<span style="background:{bg};color:#fff;padding:1px 7px;'
                f'border-radius:9px;font-size:11px;white-space:nowrap">{t}</span>')

    def theme_badges(names: list[str]) -> str:
        return " ".join(theme_badge(t) for t in names)

    def theme_action_badges(names: list[str]) -> str:
        return " ".join(
            theme_badge(t).replace("<span ", f"<span onclick=\"filterSidebar('{t}')\" ")
            for t in names
        )

    def is_num(v) -> bool:
        return isinstance(v, (int, float, np.integer, np.floating)) and not math.isnan(float(v))

    alpha_stats = {}
    _alpha_path = REPORT_DIR / "alpha_stats.json"
    if _alpha_path.exists():
        try:
            alpha_stats = json.loads(_alpha_path.read_text(encoding="utf-8"))
        except Exception:
            alpha_stats = {}

    BROAD_ALPHA_CHILDREN = {
        "半導體": ["IC設計", "晶圓代工", "封裝測試", "矽晶圓", "功率半導體"],
        "光電": ["面板"],
        "電腦週邊": ["品牌PC/NB", "伺服器/AI"],
        "網通/通訊鏈": ["連接器", "電腦週邊"],
        "其他電子": ["EMS/代工", "伺服器/AI"],
    }

    def theme_alpha20(theme: str) -> dict:
        theme_stats = alpha_stats.get("themes", {})
        exact = theme_stats.get(theme, {}).get("20d", {})
        if exact:
            return exact

        children = BROAD_ALPHA_CHILDREN.get(theme, [])
        parts = []
        for child in children:
            s20 = theme_stats.get(child, {}).get("20d", {})
            n = s20.get("n", 0)
            if is_num(s20.get("alpha")) and is_num(s20.get("winrate")) and n:
                parts.append((s20, n))
        total_n = sum(n for _, n in parts)
        if not total_n:
            return {}
        return {
            "alpha": sum(s["alpha"] * n for s, n in parts) / total_n,
            "winrate": sum(s["winrate"] * n for s, n in parts) / total_n,
            "n": total_n,
            "synthetic": True,
        }

    def classify_theme(t: dict) -> str:
        late = set(loaded_dates[-2:])
        if t["n_days"] == n_avail and t["avg_count"] >= 2:
            return "主線"
        if t["days"] and t["n_days"] <= 2 and all(d in late for d in t["days"]):
            return "新興"
        if t["n_days"] >= max(3, n_avail - 1):
            return "延續"
        if t["trend"] == "↓":
            return "降溫觀察"
        if t["n_days"] >= 2 and t["trend"] in ("→", "↑"):
            return "持平"
        return "觀察"

    def theme_reason(t: dict, alpha20: float | None) -> str:
        reasons = []
        late = set(loaded_dates[-2:])
        if t["n_days"] == n_avail:
            reasons.append("全週持續上榜")
        elif t["n_days"] >= 3:
            reasons.append("多日維持熱度")
        elif t["days"] and all(d in late for d in t["days"]):
            reasons.append("週尾新資金切入")

        if t["trend"] == "↑":
            reasons.append("週內檔數擴散")
        elif t["trend"] == "↓":
            reasons.append("週內檔數收斂")

        if alpha20 is not None:
            if alpha20 >= 0.03:
                reasons.append("歷史驗證偏正")
            elif alpha20 < 0:
                reasons.append("歷史續航偏弱")

        return "，".join(reasons) + "。" if reasons else "維持觀察，需搭配細項確認。"

    def clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
        return max(lo, min(hi, v))

    def alpha_score(a20: dict) -> float:
        alpha = a20.get("alpha")
        if not is_num(alpha):
            base = 50
        elif alpha >= 0.05:
            base = 100
        elif alpha >= 0.03:
            base = 85
        elif alpha >= 0.01:
            base = 70
        elif alpha >= 0:
            base = 55
        else:
            base = 35

        wr = a20.get("winrate")
        if is_num(wr):
            if wr >= 0.55:
                base += 5
            elif wr < 0.40:
                base -= 5

        n = a20.get("n", 0)
        if n and n < 30:
            base = base * 0.5 + 50 * 0.5
        return clamp(base)

    def action_score(theme: str, t: dict) -> dict:
        sustain = t["n_days"] / n_avail * 100 if n_avail else 0
        breadth = min(t["avg_count"] / 5, 1) * 100
        heat = clamp(t["avg_hot"] * 100)
        accel = clamp(t.get("avg_accel", 1.0) / 1.8 * 100)
        a20 = theme_alpha20(theme)
        hist = alpha_score(a20)

        sdays = sorted(t["counts"])
        if len(sdays) >= 2:
            first_count = t["counts"][sdays[0]]
            last_count = t["counts"][sdays[-1]]
            trend = 100 if last_count > first_count else (60 if last_count == first_count else 30)
        else:
            trend = 55

        late = set(loaded_dates[-2:])
        late_newcomer = bool(t["days"] and t["n_days"] <= 2 and all(d in late for d in t["days"]))
        total = (
            sustain * 0.25 +
            breadth * 0.20 +
            heat * 0.15 +
            accel * 0.10 +
            hist * 0.20 +
            trend * 0.10
        )
        if late_newcomer:
            total += 5

        parts = {
            "持續": round(sustain),
            "擴散": round(breadth),
            "熱度": round(heat),
            "加速": round(accel),
            "驗證": round(hist),
            "週內": round(trend),
        }
        return {"score": round(clamp(total)), "parts": parts}

    action_by_theme = {theme: action_score(theme, t) for theme, t in sorted_themes}
    priority_themes = sorted(
        sorted_themes,
        key=lambda x: (-action_by_theme[x[0]]["score"], -x[1]["score"])
    )

    def classify_stock_quality(days: int, m: dict) -> str:
        r1 = m.get("ret_1d", float("nan"))
        r5 = m.get("ret_5d", float("nan"))
        r20 = m.get("ret_20d", float("nan"))
        pp = m.get("price_pos", float("nan"))
        mp = m.get("month_pos", float("nan"))
        ah = m.get("accel_hist", [])
        accel_now = ah[-1] if ah else float("nan")

        weak_price = (is_num(r1) and r1 < 0) or (is_num(r5) and r5 < 0)
        weak_accel = is_num(accel_now) and accel_now < 1
        if days >= 2 and weak_price and weak_accel:
            return "轉弱觀察"
        if is_num(pp) and is_num(r20) and pp >= 0.85 and r20 >= 0.15:
            return "高位強勢"
        if days <= 2 and is_num(accel_now) and is_num(mp) and accel_now >= 1.5 and mp < 0.8:
            return "剛啟動"
        if days >= max(2, n_avail - 2) and is_num(r5) and is_num(accel_now) and r5 >= 0 and accel_now >= 1.0:
            return "主攻股"
        return "觀察"

    QUALITY_ORDER = ["主攻股", "剛啟動", "高位強勢", "轉弱觀察"]
    QUALITY_LIMIT = {"主攻股": 4, "剛啟動": 3, "高位強勢": 3, "轉弱觀察": 3}
    QUALITY_COLOR = {
        "主攻股": "#6fcf97",
        "剛啟動": "#56a7d8",
        "高位強勢": "#d6a85b",
        "轉弱觀察": "#eb5757",
    }
    QUALITY_SORT = {"主攻股": 4, "剛啟動": 3, "高位強勢": 2, "轉弱觀察": 1, "觀察": 0}

    def stock_chip(sid: str) -> str:
        name = metrics.get(sid, {}).get("name", "")
        label = f"{sid}" + (f" {name}" if name else "")
        return f'<a href="{tv_url(sid)}" target="_blank" class="pri-stock">{label}</a>'

    priority_cards_html = ""
    for theme, t in priority_themes[:5]:
        status = classify_theme(t)
        tc = THEME_COLOR.get(theme, "#74808c")
        act = action_by_theme[theme]
        score_tip = " / ".join(f"{k}{v}" for k, v in act["parts"].items())
        a20 = theme_alpha20(theme)
        alpha_v = a20.get("alpha")
        alpha_ok = is_num(alpha_v)
        alpha_c = "#6fcf97" if alpha_ok and alpha_v >= 0 else "#eb5757"
        alpha_s = f"{alpha_v:+.1%}" if alpha_ok else "—"
        alpha_meta = ""
        if is_num(a20.get("winrate")):
            wr_s = f"{a20.get('winrate'):.0%}" if is_num(a20.get("winrate")) else "—"
            alpha_meta = f'<span class="pri-alpha-sub">勝率 {wr_s}</span>'

        buckets = {k: [] for k in QUALITY_ORDER}
        for sid in sorted(t["all_stocks"], key=lambda s: (-t["stock_days"][s], s)):
            q = classify_stock_quality(t["stock_days"][sid], metrics.get(sid, {}))
            if q in buckets and len(buckets[q]) < QUALITY_LIMIT[q]:
                buckets[q].append(sid)

        quality_rows = ""
        for q in QUALITY_ORDER:
            if not buckets[q]:
                continue
            chips = " ".join(stock_chip(sid) for sid in buckets[q])
            quality_rows += (
                f'<div class="pri-qrow">'
                f'<span class="pri-qtag" style="color:{QUALITY_COLOR[q]};border-color:{QUALITY_COLOR[q]}55;'
                f'background:{QUALITY_COLOR[q]}18">{q}</span>'
                f'<div class="pri-stocks">{chips}</div>'
                f'</div>'
            )
        if not quality_rows:
            quality_rows = '<div class="pri-empty">暫無明確分層，先以細項表確認。</div>'

        priority_cards_html += f"""
        <div class="pri-card" style="border-left-color:{tc}" onclick="filterSidebar('{theme}')">
          <div class="pri-head">
            <div>
              <span class="pri-status">{status}</span>
              <span class="pri-theme" style="color:{tc}">{theme}</span>
            </div>
            <div class="pri-side">
              <div class="pri-score" title="{score_tip}">
                <span>綜合評分</span>
                <b>{act['score']}</b>
              </div>
              <div class="pri-alpha">
                <span>20日 alpha</span>
                <b style="color:{alpha_c}">{alpha_s}</b>
                {alpha_meta}
              </div>
            </div>
          </div>
          <div class="pri-metrics">
            <span>{t['n_days']}/{n_avail} 天</span>
            <span>平均 {t['avg_count']:.1f} 檔</span>
            <span>熱度 {t['avg_hot']:.0%}</span>
            <span>核心 {len(t['core'])} 檔</span>
          </div>
          <div class="pri-reason">{theme_reason(t, alpha_v if alpha_ok else None)}</div>
          <div class="pri-quality">{quality_rows}</div>
        </div>
        """

    # ── 資金輪動摘要 ──────────────────────────────────────────
    full_week = [t for t, s in sorted_themes if s["n_days"] == n_avail]
    rotation_rows = []
    if n_avail >= 3:
        late = set(loaded_dates[-2:])
        newcomers = [t for t, s in sorted_themes
                     if s["n_days"] <= 2 and all(d in late for d in s["days"])]

        early = set(loaded_dates[:2])
        faders = [t for t, s in sorted_themes
                  if s["n_days"] <= 2 and all(d in early for d in s["days"])]

        # 先動 / 跟進族群（資金輪動時序）
        full_week_set = set(full_week)
        early2 = set(loaded_dates[:2])
        late2  = set(loaded_dates[-2:])
        leaders = [
            t for t, s in sorted_themes
            if s["days"][0] in early2 and s["n_days"] >= 2 and t not in full_week_set
        ]
        followers = [
            t for t, s in sorted_themes
            if s["days"][0] in late2 and s["n_days"] >= 1
        ]
        if leaders:
            rotation_rows.append(("先動族群", leaders[:5], "週初率先發動"))
        if followers and leaders:
            rotation_rows.append(("跟進族群", followers[:5], "週尾接力出現"))
        if newcomers:
            rotation_rows.append(("週末新興", newcomers[:5], "觀察下週是否延續"))
        if faders:
            rotation_rows.append(("降溫觀察", faders[:5], "週初出現但未延續"))

    signals_html = "".join(
        f'<div class="rotation-row">'
        f'<span class="rotation-label">{label}</span>'
        f'<span class="rotation-themes">{theme_action_badges(names)}</span>'
        f'<span class="rotation-note">{note}</span>'
        f'</div>'
        for label, names, note in rotation_rows
    )
    if not signals_html:
        signals_html = '<div class="rotation-empty">本週輪動訊號不明顯，優先看上方族群決策卡。</div>'

    # ── 族群排行 ──────────────────────────────────────────────
    def _delta_cell(theme: str, t: dict, snap: dict | None) -> str:
        if not snap:
            return '<td></td>'
        if theme not in snap:
            return '<td data-val="999" style="color:#d6a85b;font-weight:700;font-size:12px">NEW</td>'
        delta = round(t["avg_count"] - snap[theme])
        if delta > 0:
            return f'<td data-val="{delta}" style="color:#6fcf97;font-weight:700">+{delta}▲</td>'
        if delta < 0:
            return f'<td data-val="{delta}" style="color:#eb5757;font-weight:700">{delta}▼</td>'
        return '<td data-val="0" style="color:#56616d">—</td>'

    _trend_html = {
        "↑": '<span style="color:#6fcf97;font-size:22px">▲</span>',
        "↓": '<span style="color:#eb5757;font-size:22px">▼</span>',
        "→": '<span style="color:#8792a0;font-size:22px">▶</span>',
        "—": '<span style="color:#56616d">—</span>',
    }
    ranking_rows = ""
    for rank, (theme, t) in enumerate(sorted_themes, 1):
        mc = MACRO_COLORS.get(t["macro"], "#74808c")
        tc = THEME_COLOR.get(theme, "#74808c")
        hp_c = heat_color(t["avg_hot"])
        act = action_by_theme[theme]
        score_tip = " / ".join(f"{k}{v}" for k, v in act["parts"].items())
        a20 = theme_alpha20(theme)
        alpha_v = a20.get("alpha")
        alpha_ok = is_num(alpha_v)
        alpha_c = "#6fcf97" if alpha_ok and alpha_v >= 0 else "#eb5757"
        alpha_s = f"{alpha_v:+.1%}" if alpha_ok else "—"
        wr_v = a20.get("winrate")
        wr_s = f"{wr_v:.0%}" if is_num(wr_v) else "—"
        day_cells = ""
        for d in week_dates:
            if d in t["counts"]:
                cnt = t["counts"][d]
                day_cells += (f'<span class="dd act" style="background:{hp_c}25;'
                              f'color:{hp_c};border:1px solid {hp_c}55">{cnt}</span>')
            else:
                day_cells += '<span class="dd"></span>'
        bar_w = int(t["n_days"] / n_avail * 100)
        core_b = (f'<span class="core-b">{len(t["core"])}</span>'
                  if t["core"] else '<span style="color:#56616d">—</span>')
        ranking_rows += f"""
        <tr class="rank-row" onclick="filterSidebar('{theme}')" data-rank="{rank}" data-raw-score="{t['score']}" data-action-score="{act['score']}">
          <td class="rk-num" data-val="{rank}">{rank}</td>
          <td data-val="{theme}">
            <div style="display:flex;flex-direction:column;gap:2px">
              <span class="theme-tag" style="background:#171d23;color:{tc};border:1px solid {tc}45">{theme}</span>
              <span style="font-size:10px;color:{mc}">{t['macro']}</span>
            </div>
          </td>
          <td><div style="display:flex;gap:3px">{day_cells}</div></td>
          <td data-val="{t['n_days']}">
            <div style="display:flex;align-items:center;gap:5px">
              <div style="height:5px;width:{bar_w}%;background:{hp_c};border-radius:3px;min-width:3px"></div>
              <span style="color:{hp_c};font-weight:700">{t['n_days']}/{n_avail}</span>
            </div>
          </td>
          <td data-val="{t['avg_hot']}" style="color:{hp_c};font-weight:600">{t['avg_hot']:.0%}</td>
          <td data-val="{t['avg_count']}" style="color:#74808c">{t['avg_count']:.1f}</td>
          <td data-val="{alpha_v if alpha_ok else -999}" style="color:{alpha_c};font-weight:600">{alpha_s}<br><span style="font-size:11px;color:#74808c;font-weight:400">勝率 {wr_s}</span></td>
          {_delta_cell(theme, t, last_snap)}
          <td class="trend-c">{_trend_html.get(t['trend'], t['trend'])}</td>
          <td data-val="{len(t['core'])}">{core_b}</td>
        </tr>"""

    # ── 個股明細表（所有上榜個股）──────────────────────────────
    # 彙整全部個股及其最佳族群（以出現天數最多的族群為準）
    all_stocks: dict[str, dict] = {}
    for theme, t in themes.items():
        for sid in t["all_stocks"]:
            days = t["stock_days"][sid]
            if sid not in all_stocks or days > all_stocks[sid]["days"]:
                all_stocks[sid] = {
                    "theme": theme, "days": days,
                    "hot":   t["avg_hot"], "accel": t["avg_accel"],
                    "ret_json": t["avg_ret"],
                }

    stock_rows = ""
    for sid, info in sorted(all_stocks.items(),
                             key=lambda x: (-x[1]["days"], -x[1]["hot"])):
        m      = metrics.get(sid, {})
        name   = m.get("name", "")
        cl     = m.get("close", float("nan"))
        mc_v   = m.get("market_cap", float("nan"))
        tv_v   = m.get("turnover", float("nan"))
        r1     = m.get("ret_1d", float("nan"))
        r5     = m.get("ret_5d", float("nan"))
        r20    = m.get("ret_20d", float("nan"))
        pp     = m.get("price_pos", float("nan"))
        mp     = m.get("month_pos", float("nan"))
        ah     = m.get("accel_hist", [float("nan")] * 5)

        days   = info["days"]
        hp     = info["hot"]
        day_c  = "#d6a85b" if days >= 4 else ("#b99a65" if days >= 3 else "#9a8f72")
        hp_c   = heat_color(hp)
        cl_s   = f"{cl:.2f}" if not (isinstance(cl, float) and math.isnan(cl)) else "—"
        mc_s   = fmt_mc(mc_v)
        tv_s   = fmt_num(tv_v) if not (isinstance(tv_v, float) and math.isnan(tv_v)) else "—"

        r1_nan  = isinstance(r1, float) and math.isnan(r1)
        r5_nan  = isinstance(r5, float) and math.isnan(r5)
        r20_nan = isinstance(r20, float) and math.isnan(r20)
        r1_s    = f"{r1:+.1%}"  if not r1_nan  else "—"
        r5_s    = f"{r5:+.1%}"  if not r5_nan  else "—"
        r20_s   = f"{r20:+.1%}" if not r20_nan else "—"

        url    = tv_url(sid)
        badge  = theme_badge(info["theme"])
        is_core = days >= (1 if n_avail <= 2 else 2)
        core_mark = '<span style="color:#ff6b6b">★</span> ' if is_core else ''
        quality = classify_stock_quality(days, m)
        q_c = QUALITY_COLOR.get(quality, "#74808c")
        q_s = QUALITY_SORT.get(quality, 0)

        stock_rows += f"""
        <tr>
          <td data-val="{sid}" data-core="{'1' if is_core else '0'}">
            <div class="stock-cell">
              <a href="{url}" target="_blank" class="sid-link">{core_mark}{sid}<span class="s-name">{' ' + name if name else ''}</span></a>
            </div>
          </td>
          <td data-val="{q_s}"><span class="q-pill" style="color:{q_c};border-color:{q_c}55;background:{q_c}18">{quality}</span></td>
          <td data-val="{info['theme']}">{badge}</td>
          <td data-val="{days}" style="color:{day_c};font-weight:700;text-align:center">{days}天</td>
          <td data-val="{mc_v if not (isinstance(mc_v,float) and math.isnan(mc_v)) else -999}" style="text-align:right;color:#74808c">{mc_s}</td>
          <td data-val="{tv_v if not (isinstance(tv_v,float) and math.isnan(tv_v)) else -999}" style="text-align:right;color:#56a7d8">{tv_s}</td>
          <td>{sparkline(ah)}</td>
          <td data-val="{r5 if not r5_nan else -999}" style="text-align:right;color:{ret_color(r5)};font-weight:600">{r5_s}</td>
          <td data-val="{r20 if not r20_nan else -999}" style="text-align:right;color:{ret_color(r20)};font-weight:600">{r20_s}</td>
          <td data-val="{pp if is_num(pp) else -999}">{pos_bar(pp)}</td>
          <td data-val="{mp if is_num(mp) else -999}">{pos_bar(mp, ("#56a7d8","#9b8fd3","#74808c"))}</td>
          <td data-val="{cl if not (isinstance(cl,float) and math.isnan(cl)) else -999}" style="text-align:right;color:{ret_color(r1) if not r1_nan else '#74808c'}">{cl_s}</td>
          <td data-val="{r1 if not r1_nan else -999}" style="text-align:right;color:{ret_color(r1)};font-weight:600">{r1_s}</td>
        </tr>"""

    # ── 右欄個股索引 ──────────────────────────────────────────
    sidebar_items = ""
    for i, (theme, t) in enumerate(sorted_themes):
        n      = t["n_days"]
        badge_c= "#d6a85b" if n >= 4 else ("#9a8f72" if n >= 2 else "#74808c")
        mc_c   = MACRO_COLORS.get(t["macro"], "#74808c")
        tc     = THEME_COLOR.get(theme, "#74808c")

        stocks_html = ""
        for sid in sorted(t["all_stocks"], key=lambda s: -t["stock_days"][s]):
            m_name  = metrics.get(sid, {}).get("name", "")
            days_s  = t["stock_days"][sid]
            is_core = sid in t["core"]
            sup     = f'<sup class="dbadge">{days_s}</sup>' if days_s > 1 else ""
            cls     = " core" if is_core else ""
            label   = f"{sid}" + (f" {m_name}" if m_name else "")
            stocks_html += (
                f'<a href="{tv_url(sid)}" target="_blank" class="sidx-s{cls}">'
                f'{label}{sup}</a>'
            )

        open_cls = " open" if i < 3 else ""
        sidebar_items += f"""
        <div class="sidx-g" data-theme="{theme}">
          <div class="sidx-h{open_cls}" onclick="toggleSidebar(this)">
            <span class="sidx-theme" style="color:{tc}">{theme}</span>
            <div style="display:flex;align-items:center;gap:5px">
              <span class="sidx-badge" style="background:{badge_c}20;color:{badge_c};border:1px solid {badge_c}40">{n}天</span>
              <span class="sidx-cnt">{len(t['all_stocks'])}檔</span>
              <span class="sidx-arr">▼</span>
            </div>
          </div>
          <div class="sidx-b{open_cls}">{stocks_html}</div>
        </div>"""

    # ── 統計 ─────────────────────────────────────────────────
    total_stocks = len(all_stocks)
    total_core   = sum(1 for s in all_stocks.values() if s["days"] >= (1 if n_avail <= 2 else 2))
    day_lbl_str  = " / ".join(DAY_LABELS[d.weekday()] for d in loaded_dates)

    # ── 歷史驗證區塊 ──────────────────────────────────────────
    alpha_footnote_html = ""
    _alpha_path = REPORT_DIR / "alpha_stats.json"
    if _alpha_path.exists():
        try:
            _ad     = json.loads(_alpha_path.read_text(encoding="utf-8"))
            _ov20   = _ad.get("overall", {}).get("20d", {})
            _period = _ad.get("overall", {}).get("period", "")
            _n      = _ov20.get("n", 0)
            alpha_footnote_html = (
                f'<div style="font-size:11px;color:#3d4852;margin-top:8px">'
                f'歷史驗證：N = {_n:,} · {_period} · 信號條件 hot_pct ≥ 75%'
                f'・alpha = 個股報酬 − 同期 0050 報酬</div>'
            )
        except Exception:
            pass

    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>熱門股週報 {week_label}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#101418;color:#d2d8df;font-family:'Segoe UI','Microsoft JhengHei',system-ui,sans-serif;font-size:16px;line-height:1.5}}

/* ── Layout ── */
.layout{{display:grid;grid-template-columns:1fr 540px;min-height:100vh}}
.main{{padding:24px 28px;overflow-y:auto;min-width:0}}
.sidebar{{background:#171d23;border-left:1px solid #2b3540;padding:16px;overflow-y:auto;position:sticky;top:0;height:100vh}}

/* ── Header ── */
.hd-title{{font-size:36px;font-weight:700;color:#d2d8df;letter-spacing:.01em;margin-bottom:4px}}
.hd-sub{{color:#8792a0;font-size:14px;margin-bottom:18px}}
.stat-row{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:26px}}
.stat-box{{background:#171d23;border:1px solid #2b3540;border-radius:9px;padding:12px 20px;min-width:110px}}
.stat-n{{font-size:28px;font-weight:700;color:#6fcf97}}
.stat-lbl{{font-size:14px;color:#8792a0;margin-top:2px}}

/* ── Sections ── */
.sec{{margin-bottom:28px}}
.sec-title{{font-size:16px;font-weight:600;color:#8792a0;text-transform:uppercase;letter-spacing:.07em;margin-bottom:12px;padding-bottom:6px;border-bottom:1px solid #2b3540}}
.sec-hint{{font-size:11px;font-weight:400;color:#56616d;text-transform:none;letter-spacing:0;margin-left:8px;vertical-align:middle}}

/* ── Priority cards ── */
.pri-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:12px}}
.pri-card{{background:#171d23;border:1px solid #2b3540;border-left:4px solid #74808c;border-radius:8px;padding:14px 16px;cursor:pointer;transition:border-color .12s,background .12s}}
.pri-card:hover{{background:#1a2128;border-color:#3b4652}}
.pri-head{{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:10px}}
.pri-status{{color:#d2d8df;font-weight:700;font-size:15px;margin-right:8px}}
.pri-theme{{font-size:20px;font-weight:800}}
.pri-side{{display:flex;gap:16px;align-items:flex-start}}
.pri-score{{display:flex;flex-direction:column;align-items:flex-end;color:#56616d;font-size:11px;white-space:nowrap}}
.pri-score b{{font-size:22px;line-height:1;color:#d6a85b}}
.pri-alpha{{display:flex;flex-direction:column;align-items:flex-end;gap:1px;white-space:nowrap;color:#56616d;font-size:11px}}
.pri-alpha b{{font-size:16px;line-height:1.1}}
.pri-alpha-sub{{font-size:11px;color:#b86f6f;font-weight:700}}
.pri-metrics{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:9px}}
.pri-metrics span{{background:#101418;border:1px solid #2b3540;color:#8792a0;border-radius:4px;padding:2px 7px;font-size:12px}}
.pri-reason{{color:#d2d8df;font-size:15px;line-height:1.55;margin-bottom:10px}}
.pri-quality{{display:flex;flex-direction:column;gap:7px}}
.pri-qrow{{display:grid;grid-template-columns:76px 1fr;gap:8px;align-items:flex-start}}
.pri-qtag{{display:inline-flex;justify-content:center;border:1px solid;border-radius:4px;padding:2px 6px;font-size:12px;font-weight:700;white-space:nowrap}}
.pri-stocks{{display:flex;gap:6px;flex-wrap:wrap}}
.pri-stock{{color:#d2d8df;text-decoration:none;background:#101418;border:1px solid #2b3540;border-radius:4px;padding:2px 7px;font-size:13px;line-height:1.5}}
.pri-stock:hover{{border-color:#56a7d8;color:#56a7d8}}
.pri-empty{{color:#56616d;font-size:13px}}

/* ── Rotation summary ── */
.rotation-box{{background:#171d23;border:1px solid #2b3540;border-radius:8px;padding:10px 14px}}
.rotation-row{{display:grid;grid-template-columns:88px 1fr auto;gap:10px;align-items:center;padding:7px 0;border-bottom:1px solid #222b34}}
.rotation-row:last-child{{border-bottom:none}}
.rotation-label{{color:#d2d8df;font-weight:700;font-size:13px;white-space:nowrap}}
.rotation-themes{{display:flex;gap:5px;flex-wrap:wrap}}
.rotation-themes span{{cursor:pointer}}
.rotation-themes span:hover{{filter:brightness(1.15)}}
.rotation-note{{color:#56616d;font-size:12px;white-space:nowrap}}
.rotation-empty{{color:#56616d;font-size:13px;padding:4px 0}}

/* ── Ranking table ── */
.rk-tbl{{width:100%;border-collapse:collapse}}
.rk-tbl th{{color:#8792a0;font-size:13px;font-weight:400;text-align:left;padding:10px 12px;border-bottom:2px solid #2b3540;white-space:nowrap;cursor:pointer;user-select:none;position:sticky;top:0;background:#171d23}}
.rk-tbl th:hover{{color:#d2d8df}}
.rk-tbl td{{padding:9px 12px;border-bottom:1px solid #171d23;vertical-align:middle}}
.rank-row{{cursor:pointer;transition:background .12s}}
.rank-row:hover{{background:#171d23}}
.rk-num{{color:#56616d;font-weight:600;font-size:18px;width:32px}}
.theme-tag{{padding:3px 10px;border-radius:5px;font-size:16px;font-weight:600;white-space:nowrap;display:inline-block}}
.dd{{display:inline-flex;align-items:center;justify-content:center;width:30px;height:26px;border-radius:4px;font-size:15px;font-weight:600;background:#101418;color:#56616d;border:1px solid #2b3540}}
.trend-c{{text-align:center;color:#56616d;font-size:18px}}
.core-b{{background:#2a2419;color:#d6a85b;border:1px solid #d6a85b40;padding:2px 9px;border-radius:10px;font-size:14px;font-weight:700}}
.rank-tools{{display:flex;gap:8px;align-items:center;margin-bottom:10px;flex-wrap:wrap}}
.rank-toggle{{background:#171d23;color:#8792a0;border:1px solid #2b3540;border-radius:5px;padding:5px 10px;font-size:13px;cursor:pointer}}
.rank-toggle.active{{color:#d6a85b;border-color:#d6a85b66;background:#2a2419}}

/* ── Stock table ── */
.stk-tbl{{width:100%;border-collapse:collapse}}
.stk-tbl th{{color:#8792a0;font-size:13px;font-weight:400;text-align:left;padding:10px 12px;border-bottom:2px solid #2b3540;white-space:nowrap;cursor:pointer;user-select:none;background:#171d23;position:sticky;top:0}}
.stk-tbl th:hover{{color:#d2d8df}}
.stk-tbl th.sort-asc::after{{content:' ↑';color:#6fcf97}}
.stk-tbl th.sort-desc::after{{content:' ↓';color:#eb5757}}
.stk-tbl td{{padding:9px 12px;border-bottom:1px solid #171d23;vertical-align:middle;white-space:nowrap}}
.stk-tbl tr:hover td{{background:#171d23}}
.stock-cell{{display:flex;align-items:center;gap:8px;flex-wrap:wrap}}
.sid-link{{color:#56a7d8;text-decoration:none;font-weight:700;font-family:monospace;font-size:17px}}
.sid-link:hover{{color:#8fc7e5;text-decoration:underline}}
.s-name{{color:#8792a0;font-size:15px}}
.sid-link:hover .s-name{{color:#8fc7e5}}
.q-pill{{display:inline-flex;justify-content:center;min-width:64px;border:1px solid;border-radius:4px;padding:2px 6px;font-size:12px;font-weight:700;white-space:nowrap}}

/* ── Search ── */
.search-bar{{background:#101418;border:1px solid #2b3540;border-radius:7px;padding:8px 14px;color:#d2d8df;font-size:16px;width:280px;margin-bottom:14px;outline:none}}
.search-bar::placeholder{{color:#56616d}}
.search-bar:focus{{border-color:#56a7d8}}

/* ── Sidebar ── */
.sd-title{{font-size:16px;font-weight:600;color:#8792a0;text-transform:uppercase;letter-spacing:.06em;margin-bottom:5px}}
.sd-hint{{font-size:14px;color:#56616d;margin-bottom:12px;line-height:1.6}}
.sidx-g{{margin-bottom:3px;border:1px solid #2b3540;border-radius:7px;overflow:hidden}}
.sidx-g.hi{{border-color:#d6a85b}}
.sidx-h{{display:flex;justify-content:space-between;align-items:center;padding:9px 12px;cursor:pointer;background:#101418;transition:background .12s;user-select:none}}
.sidx-h:hover,.sidx-h.open{{background:#171d23}}
.sidx-theme{{font-size:16px;font-weight:700}}
.sidx-badge{{padding:2px 8px;border-radius:3px;font-size:14px;font-weight:700}}
.sidx-cnt{{color:#56616d;font-size:14px}}
.sidx-arr{{color:#56616d;font-size:14px;transition:transform .18s}}
.sidx-h.open .sidx-arr{{transform:rotate(180deg)}}
.sidx-b{{display:none;padding:9px 10px;background:#101418;border-top:1px solid #2b3540;flex-wrap:wrap;gap:6px}}
.sidx-b.open{{display:flex}}
.sidx-s{{color:#8792a0;text-decoration:none;font-size:15px;padding:4px 9px;background:#171d23;border-radius:5px;white-space:nowrap;transition:background .12s;line-height:1.4}}
.sidx-s:hover{{background:#2b3540;color:#d2d8df}}
.sidx-s.core{{color:#d6a85b;background:#2a2419;border:1px solid #d6a85b33}}
.sidx-s.core:hover{{background:#332b1d;color:#e3bc75}}
.dbadge{{font-size:10px;font-weight:800;color:#ff2d2d;vertical-align:super}}

@media (max-width: 900px) {{
  .layout {{
    grid-template-columns: 1fr;
  }}

  .sidebar {{
    position: relative;
    height: auto;
    border-left: none;
    border-top: 1px solid #2b3540;
  }}

  .main {{
    padding: 14px;
  }}

  .rk-tbl,
  .stk-tbl {{
    font-size: 12px;
  }}

  .search-bar {{
    width: 100%;
  }}

  .pri-grid {{
    grid-template-columns: 1fr;
  }}

  .pri-head {{
    flex-direction: column;
  }}

  .pri-alpha {{
    align-items: flex-start;
  }}

  .pri-side {{
    width:100%;
    justify-content:space-between;
  }}

  .pri-score {{
    align-items:flex-start;
  }}

  .rotation-row {{
    grid-template-columns:1fr;
    gap:4px;
  }}

  .rotation-note {{
    white-space:normal;
  }}
}}
</style>
</head>
<body>
<div class="layout">

<!-- ══ 主欄 ══ -->
<div class="main">
  <div class="hd-title">熱門股週報</div>
  <div class="hd-sub">{week_label} ・ 已統計：{day_lbl_str}</div>
  <div class="stat-row">
    <div class="stat-box"><div class="stat-n" style="color:#56a7d8">{len(themes)}</div><div class="stat-lbl" style="color:#56a7d8">族群排行</div></div>
    <div class="stat-box"><div class="stat-n" style="color:#6fcf97">{total_stocks}</div><div class="stat-lbl" style="color:#6fcf97">選股明細</div></div>
    <div class="stat-box"><div class="stat-n" style="color:#ff6b6b">{total_core}</div><div class="stat-lbl" style="color:#ff6b6b"><span>★</span> 核心個股</div></div>
    <div class="stat-box"><div class="stat-n" style="color:#9b8fd3">{n_avail}/5</div><div class="stat-lbl" style="color:#9b8fd3">已統計交易日</div></div>
  </div>

  <div class="sec">
    <div class="sec-title"><span style="color:#d6a85b">本週優先研究</span><span class="sec-hint">先看結論；細項表保留在下方</span></div>
    <div class="pri-grid">{priority_cards_html}</div>
  </div>

  <div class="sec">
    <div class="sec-title"><span style="color:#8792a0">資金輪動摘要</span><span class="sec-hint">補充脈絡，不取代上方優先研究</span></div>
    <div class="rotation-box">{signals_html}</div>
  </div>

  <div class="sec">
    <div class="sec-title"><span style="color:#56a7d8">族群排行</span><span class="sec-hint">點擊列 → 右欄定位</span></div>
    <div class="rank-tools">
      <button class="rank-toggle active" onclick="setRankMode('raw', this)">原始熱度排序</button>
      <button class="rank-toggle" onclick="setRankMode('action', this)">綜合評分排序</button>
    </div>
    <table class="rk-tbl" id="rk-tbl">
      <thead><tr>
        <th onclick="sortRank(this,0)">#</th>
        <th onclick="sortRank(this,1)">族群</th>
        <th style="min-width:130px;white-space:normal">出現日 · 一&nbsp;二&nbsp;三&nbsp;四&nbsp;五<br><span style="font-size:11px;font-weight:400;color:#56616d;letter-spacing:0;text-transform:none">(數字 = 當日上榜檔數)</span></th>
        <th onclick="sortRank(this,3)">持續度</th>
        <th onclick="sortRank(this,4)">平均熱度</th>
        <th onclick="sortRank(this,5)">平均檔數</th>
        <th onclick="sortRank(this,6)">20日 alpha · 勝率</th>
        <th onclick="sortRank(this,7)">較前週</th>
        <th>週內趨勢</th>
        <th onclick="sortRank(this,9)">核心股</th>
      </tr></thead>
      <tbody>{ranking_rows}</tbody>
    </table>
    {alpha_footnote_html}
  </div>

  <div class="sec">
    <div class="sec-title"><span style="color:#6fcf97">選股明細</span><span class="sec-hint"><span style="color:#ff6b6b">★</span> = 連續上榜 ≥2天</span></div>
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px">
      <input class="search-bar" id="search" placeholder="搜尋代號 / 名稱 / 族群..." oninput="filterTable()" style="margin-bottom:0">
      <button onclick="exportCSV()" style="background:#27ae60;color:#fff;border:none;border-radius:7px;padding:8px 18px;font-size:15px;font-weight:600;cursor:pointer;white-space:nowrap">匯出 CSV</button>
    </div>
    <table class="stk-tbl" id="stk-tbl">
      <thead><tr>
        <th onclick="sortStk(this,0)" style="min-width:160px">選股</th>
        <th onclick="sortStk(this,1)" style="min-width:80px">分層</th>
        <th onclick="sortStk(this,2)" style="min-width:90px">族群</th>
        <th onclick="sortStk(this,3)" style="text-align:center">上榜天數</th>
        <th onclick="sortStk(this,4)" style="text-align:right">市值</th>
        <th onclick="sortStk(this,5)" style="text-align:right">成交值</th>
        <th>加速趨勢(5日)</th>
        <th onclick="sortStk(this,7)" style="text-align:right">5日%</th>
        <th onclick="sortStk(this,8)" style="text-align:right">20日%</th>
        <th onclick="sortStk(this,9)" style="min-width:80px">3年高位<br><small style="font-weight:400;color:#8792a0">現價/3年高</small></th>
        <th onclick="sortStk(this,10)" style="min-width:80px">月內位置<br><small style="font-weight:400;color:#8792a0">月內區間</small></th>
        <th onclick="sortStk(this,11)" style="text-align:right">成交價</th>
        <th onclick="sortStk(this,12)" style="text-align:right">1日%</th>
      </tr></thead>
      <tbody>{stock_rows}</tbody>
    </table>
  </div>
</div>

<!-- ══ 右欄 ══ -->
<div class="sidebar">
  <div class="sd-title">個股索引</div>
  <div class="sd-hint">
    <span style="color:#d6a85b">■</span> 琥珀色 = 核心股（≥2天）・上標 = 出現天數<br>
    點擊族群展開 ・ 點左欄列自動定位
  </div>
  <div id="sidx">{sidebar_items}</div>
</div>
</div>

<script>
// ── Sidebar toggle ──
function toggleSidebar(hdr) {{
  hdr.classList.toggle('open');
  hdr.nextElementSibling.classList.toggle('open');
}}
function filterSidebar(theme) {{
  const sidx = document.getElementById('sidx');
  document.querySelectorAll('.sidx-g').forEach(g => {{
    const match = g.dataset.theme === theme;
    g.classList.toggle('hi', match);
    if (match) {{
      const h = g.querySelector('.sidx-h');
      const b = g.querySelector('.sidx-b');
      h.classList.add('open'); b.classList.add('open');
      sidx.insertBefore(g, sidx.firstChild);
      sidx.scrollTop = 0;
    }}
  }});
}}

// ── Table search ──
function filterTable() {{
  const q = document.getElementById('search').value.toLowerCase();
  document.querySelectorAll('#stk-tbl tbody tr').forEach(r => {{
    r.style.display = r.textContent.toLowerCase().includes(q) ? '' : 'none';
  }});
}}

// ── Sort helpers ──
let rankDir = {{}}, stkDir = {{}};

function sortByCol(tbodyId, thEl, col, dirMap) {{
  const tbody = document.querySelector('#' + tbodyId + ' tbody');
  const rows  = Array.from(tbody.querySelectorAll('tr'));
  const dir   = dirMap[col] = -(dirMap[col] || 1);
  rows.sort((a, b) => {{
    const as = a.cells[col]?.dataset.val ?? '';
    const bs = b.cells[col]?.dataset.val ?? '';
    const av = parseFloat(as), bv = parseFloat(bs);
    if (isNaN(av) || isNaN(bv)) return as.localeCompare(bs, 'zh-TW') * dir;
    return (av - bv) * dir;
  }});
  rows.forEach(r => tbody.appendChild(r));
  tbody.closest('table').querySelectorAll('th').forEach(h => h.className = h.className.replace(/sort-(asc|desc)/g,'').trim());
  thEl.classList.add(dir === 1 ? 'sort-asc' : 'sort-desc');
}}

function sortRank(th, col)  {{ sortByCol('rk-tbl',   th, col, rankDir);  }}

function setRankMode(mode, btn) {{
  const tbody = document.querySelector('#rk-tbl tbody');
  const rows = Array.from(tbody.querySelectorAll('tr'));
  const key = mode === 'action' ? 'actionScore' : 'rawScore';
  rows.sort((a, b) => parseFloat(b.dataset[key]) - parseFloat(a.dataset[key]));
  rows.forEach((r, i) => {{
    r.cells[0].dataset.val = i + 1;
    r.cells[0].innerText = i + 1;
    tbody.appendChild(r);
  }});
  document.querySelectorAll('.rank-toggle').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.querySelector('#rk-tbl').querySelectorAll('th').forEach(h => h.className = h.className.replace(/sort-(asc|desc)/g,'').trim());
}}

let col0Mode = -1;
function sortStk(th, col) {{
  if (col === 0) {{
    col0Mode = (col0Mode + 1) % 2;
    const tbody = document.querySelector('#stk-tbl tbody');
    const rows  = Array.from(tbody.querySelectorAll('tr'));
    if (col0Mode === 0) {{
      rows.sort((a, b) => {{
        const ca = +(a.cells[0].dataset.core || 0);
        const cb = +(b.cells[0].dataset.core || 0);
        if (ca !== cb) return cb - ca;
        return (a.cells[0].dataset.val || '').localeCompare(b.cells[0].dataset.val || '');
      }});
      tbody.closest('table').querySelectorAll('th').forEach(h => h.className = h.className.replace(/sort-(asc|desc)/g,'').trim());
      th.classList.add('sort-desc');
    }} else {{
      rows.sort((a, b) => (a.cells[0].dataset.val || '').localeCompare(b.cells[0].dataset.val || ''));
      tbody.closest('table').querySelectorAll('th').forEach(h => h.className = h.className.replace(/sort-(asc|desc)/g,'').trim());
      th.classList.add('sort-asc');
    }}
    rows.forEach(r => tbody.appendChild(r));
  }} else {{
    sortByCol('stk-tbl', th, col, stkDir);
  }}
}}

// ── CSV 匯出 ──
function exportCSV() {{
  const headers = ['代號','名稱','分層','族群','上榜天數','市值(億)','成交值(億)','加速(最新)','5日%','20日%','3年高位%','月內位置%','成交價','1日%'];
  const rows = [headers.join(',')];
  document.querySelectorAll('#stk-tbl tbody tr').forEach(tr => {{
    if (tr.style.display === 'none') return;
    const c = tr.cells;
    const sid   = c[0].dataset.val || '';
    const name  = c[0].querySelector('.s-name')?.innerText.trim() || '';
    const quality = c[1].innerText.trim() || '';
    const theme = c[2].dataset.val || '';
    const days  = c[3].dataset.val || '';
    const mc_raw = parseFloat(c[4].dataset.val);
    const tv_raw = parseFloat(c[5].dataset.val);
    const mc  = isNaN(mc_raw) || mc_raw <= 0 ? '' : (mc_raw / 1e8).toFixed(0);
    const tv  = isNaN(tv_raw) || tv_raw <= 0 ? '' : (tv_raw / 1e8).toFixed(0);
    const ac  = c[6].innerText.replace(/[^\d.×]/g,'').trim() || '';
    const pp_m = c[9].innerText.match(/(\d+)%/);
    const mp_m = c[10].innerText.match(/(\d+)%/);
    const pp  = pp_m ? pp_m[1] + '%' : '';
    const mp  = mp_m ? mp_m[1] + '%' : '';
    const fmt = v => {{ const n = parseFloat(v); return isNaN(n) || n <= -900 ? '' : (n * 100).toFixed(1) + '%'; }};
    const r5  = fmt(c[7].dataset.val);
    const r20 = fmt(c[8].dataset.val);
    const price = c[11].dataset.val || '';
    const r1  = fmt(c[12].dataset.val);
    rows.push([sid,name,quality,theme,days,mc,tv,ac,r5,r20,pp,mp,price,r1].map(v=>`"${{v}}"`).join(','));
  }});
  const blob = new Blob(['﻿' + rows.join('\\n')], {{type:'text/csv;charset=utf-8'}});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `熱門股週報_{loaded_dates[-1]}.csv`;
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}}

// ── Init: open first 3 sidebar groups ──
document.querySelectorAll('.sidx-g').forEach((g, i) => {{
  if (i < 3) {{
    g.querySelector('.sidx-h').classList.add('open');
    g.querySelector('.sidx-b').classList.add('open');
  }}
}});
</script>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────
#  主程式
# ─────────────────────────────────────────────────────────────────

def main():
    import argparse
    import finlab
    finlab.login(os.environ["FINLAB_API_TOKEN"])

    p = argparse.ArgumentParser(description="熱門股週報生成器")
    p.add_argument("--date",       help="指定週報結束日 YYYY-MM-DD（預設本週）")
    p.add_argument("--no-browser", action="store_true", dest="no_browser",
                   help="產出後不自動開啟瀏覽器")
    args = p.parse_args()

    if args.date:
        end = date.fromisoformat(args.date)
        week_dates = get_week_dates(end)
    else:
        week_dates = _auto_week_dates_from_finlab()
    week_data    = build_week_data_from_finlab(week_dates)

    if not week_data:
        print(f"FinLab database 找不到本週可用交易資料（{week_dates[0]} ~ {week_dates[-1]}）")
        return

    loaded_dates = sorted(week_data.keys())
    print(f"載入 {len(loaded_dates)} 天：{', '.join(str(d) for d in loaded_dates)}")

    themes, _ = aggregate(week_data)
    print(f"彙整 {len(themes)} 個族群")

    all_sids = {s for t in themes.values() for s in t["all_stocks"]}
    print(f"取得 {len(all_sids)} 檔個股資料...")
    finlab = load_finlab_data(all_sids)

    last_snap  = load_last_snapshot(loaded_dates[0])
    week_label = f"{loaded_dates[0].strftime('%Y/%m/%d')} ~ {loaded_dates[-1].strftime('%m/%d')}"
    html       = render_html(themes, week_dates, loaded_dates, finlab, week_label, last_snap)

    REPORT_DIR.mkdir(exist_ok=True)
    out = REPORT_DIR / f"熱門股週報_{loaded_dates[-1]}.html"
    out.write_text(html, encoding="utf-8")
    print(f"週報已輸出：{out}")

    save_snapshot(themes, loaded_dates[-1])
    print(f"Snapshot 已儲存：{SNAPSHOT_DIR / str(loaded_dates[-1])}.json")

    if not args.no_browser:
        os.startfile(str(out))


if __name__ == "__main__":
    main()
