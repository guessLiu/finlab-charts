"""
Forward Return Validation
計算 hot_pct 信號的 market-adjusted alpha（5日、20日）。
跑完輸出 reports/alpha_stats.json，週報自動讀取。

執行方式：
    python validate_alpha.py
"""
from dotenv import load_dotenv
load_dotenv()

import json, os, sys
import numpy as np
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).parent
REPORT_DIR = BASE_DIR / "reports"

sys.path.insert(0, str(BASE_DIR))
from theme_map import THEME

# ── 與週報相同的篩選參數 ──────────────────────────────────────────
N_HIST           = 252
PERCENTILE_MIN   = 0.75
ACCEL_MIN        = 0.75
MARKET_CAP_MIN   = 30e8
TURNOVER_ABS_MIN = 30e8

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

MARKET_PROXY = "0050"   # 元大台灣50 作為大盤 benchmark


def _stats(series: pd.Series) -> dict:
    s = series.dropna()
    if len(s) < 20:
        return {}
    return {
        "alpha":   round(float(s.mean()), 4),
        "winrate": round(float((s > 0).mean()), 3),
        "n":       int(len(s)),
    }


def run():
    import finlab
    from finlab import data as fdata

    finlab.login(os.environ["FINLAB_API_TOKEN"])

    print("載入歷史資料（約需 1~2 分鐘）...")
    close        = pd.DataFrame(fdata.get("price:收盤價"))
    turnover_raw = pd.DataFrame(fdata.get("price:成交金額"))
    market_value = pd.DataFrame(fdata.get("etl:market_value"))
    company_info = fdata.get("company_basic_info")
    if not isinstance(company_info, pd.DataFrame):
        company_info = pd.DataFrame(company_info)

    for df in (close, turnover_raw, market_value):
        df.index = pd.to_datetime(df.index)
    turnover_raw = turnover_raw.reindex(close.index)
    market_value = market_value.reindex(close.index).ffill()

    # ── 個股篩選 ────────────────────────────────────────────────
    valid_sids = [c for c in close.columns
                  if len(str(c)) == 4 and not str(c).startswith("0")]

    # ── 大盤 benchmark（0050）────────────────────────────────────
    if MARKET_PROXY in close.columns:
        mkt = close[MARKET_PROXY]
    else:
        print(f"警告：找不到 {MARKET_PROXY}，改用等權重大盤")
        mkt = close[valid_sids].pct_change(fill_method=None).mean(axis=1).add(1).cumprod()

    mkt_fwd_5d  = mkt.pct_change(5, fill_method=None).shift(-5)
    mkt_fwd_20d = mkt.pct_change(20, fill_method=None).shift(-20)

    # ── 縮小到有效個股 ──────────────────────────────────────────
    close        = close[valid_sids]
    turnover_raw = turnover_raw.reindex(columns=valid_sids)
    market_value = market_value.reindex(columns=valid_sids)

    # ── 向量化信號計算 ───────────────────────────────────────────
    print("計算 hot_pct 信號（向量化）...")
    turnover_rate = turnover_raw.div(market_value)
    turn_3d  = turnover_rate.rolling(3, min_periods=2).sum()
    hot_pct  = turn_3d.rolling(N_HIST, min_periods=60).rank(pct=True)
    accel    = turn_3d / turn_3d.shift(3).replace(0, np.nan)

    signal = (
        (hot_pct  >= PERCENTILE_MIN) &
        (accel    >= ACCEL_MIN) &
        (market_value >= MARKET_CAP_MIN) &
        (turnover_raw >= TURNOVER_ABS_MIN)
    )
    # 最後 20 個交易日沒有完整的 20 日 forward return，排除
    signal.iloc[-20:] = False

    # ── Forward return (market-adjusted alpha) ───────────────────
    print("計算 forward return...")
    fwd_5d  = close.pct_change(5,  fill_method=None).shift(-5)
    fwd_20d = close.pct_change(20, fill_method=None).shift(-20)
    alpha_5d  = fwd_5d.sub(mkt_fwd_5d,  axis=0)
    alpha_20d = fwd_20d.sub(mkt_fwd_20d, axis=0)

    # ── Theme mapping ────────────────────────────────────────────
    broad_cat = company_info.set_index("stock_id")[company_info.columns[3]]

    def map_theme(sid: str) -> str:
        t = THEME.get(sid, "")
        if not t:
            t = BROAD_MAP.get(broad_cat.get(sid, ""), "")
        return t if t in KEEP_THEMES else ""

    theme_of = {sid: map_theme(sid) for sid in valid_sids}

    # ── 整體統計 ─────────────────────────────────────────────────
    print("彙整統計...")
    flat_5d  = alpha_5d[signal].stack().dropna()
    flat_20d = alpha_20d[signal].stack().dropna()

    period_start = close.index[N_HIST].strftime("%Y-%m")
    period_end   = close.index[-21].strftime("%Y-%m")

    overall = {
        "5d":     _stats(flat_5d),
        "20d":    _stats(flat_20d),
        "period": f"{period_start} ~ {period_end}",
    }
    print(f"  整體 5日 alpha={overall['5d']['alpha']:.2%}  "
          f"勝率={overall['5d']['winrate']:.1%}  N={overall['5d']['n']:,}")

    # ── 按族群統計 ───────────────────────────────────────────────
    themes_out: dict[str, dict] = {}
    for sid in valid_sids:
        theme = theme_of.get(sid, "")
        if not theme:
            continue
        sig_mask = signal[sid] if sid in signal.columns else None
        if sig_mask is None or not sig_mask.any():
            continue
        a5  = alpha_5d[sid][sig_mask].dropna()
        a20 = alpha_20d[sid][sig_mask].dropna()
        if sid not in themes_out:
            themes_out[theme] = {"a5": [], "a20": []}
        themes_out[theme]["a5"].extend(a5.tolist())
        themes_out[theme]["a20"].extend(a20.tolist())

    themes_stats = {}
    for theme, data in themes_out.items():
        s5  = _stats(pd.Series(data["a5"]))
        s20 = _stats(pd.Series(data["a20"]))
        if not s5:
            continue
        themes_stats[theme] = {"5d": s5, "20d": s20}
        print(f"  {theme:<12} 5日 alpha={s5['alpha']:.2%}  勝率={s5['winrate']:.1%}  N={s5['n']}")

    result = {"overall": overall, "themes": themes_stats}
    REPORT_DIR.mkdir(exist_ok=True)
    out = REPORT_DIR / "alpha_stats.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n完成 → {out}")


if __name__ == "__main__":
    run()
