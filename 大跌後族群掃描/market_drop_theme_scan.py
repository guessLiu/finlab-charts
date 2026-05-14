from __future__ import annotations

import argparse
import importlib.util
import io
import json
import sys
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv


DEFAULT_RESEARCH_DIR = Path(r"C:\Users\Liu Family\Finlab\research")
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_THEME_MAP = SCRIPT_DIR / "theme_map.py"

BROAD_MAP = {
    "半導體業": "半導體",
    "電子零組件業": "電子零組件",
    "光電業": "光電",
    "電腦及週邊設備業": "電腦週邊",
    "通信網路業": "網通",
    "電機機械": "電機",
    "其他電子業": "其他電子",
    "電子通路業": "電子通路",
    "資訊服務業": "資訊服務",
    "數位雲端": "數位雲端",
    "電子工業": "電子工業",
    "生技醫療業": "生技醫療",
    "化學工業": "化學",
    "汽車工業": "汽車",
    "機械工業": "機械",
    "玻璃陶瓷": "玻璃陶瓷",
    "航運業": "航運",
    "金融保險業": "金融",
    "水泥工業": "水泥",
    "鋼鐵工業": "鋼鐵",
    "塑膠工業": "塑膠",
    "紡織纖維": "紡織",
    "觀光餐旅": "觀光",
    "貿易百貨": "百貨",
    "食品工業": "食品",
    "建材營造": "營建",
    "油電燃氣業": "油電燃氣",
}

# 族群掃描範圍設定：將使用者指定的大分類對應到 company_basic_info 中的原始產業別名稱
SECTOR_BROAD_CATS: dict[str, set[str]] = {
    "電子類股": {
        "半導體業", "電子零組件業", "光電業", "電腦及週邊設備業",
        "通信網路業", "其他電子業", "電子通路業", "資訊服務業", "數位雲端",
    },
    "玻璃陶瓷類": {"玻璃陶瓷"},
    "機電類": {"電機機械"},
    "電子工業類": {"電子工業"},
}
DEFAULT_SECTORS = ["電子類股", "玻璃陶瓷類", "機電類", "電子工業類"]

def pct(x: float | int | None) -> str:
    if pd.isna(x):
        return ""
    return f"{float(x) * 100:,.2f}%"


def money_100m(x: float | int | None) -> str:
    if pd.isna(x):
        return ""
    return f"{float(x) / 1e8:,.1f}億"


def load_theme_maps(path: Path) -> tuple[dict[str, str], dict[str, list[str]]]:
    spec = importlib.util.spec_from_file_location("theme_map", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"無法載入族群表: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    theme = {str(k): str(v) for k, v in getattr(module, "THEME", {}).items()}
    theme_multi = {
        str(k): [str(x) for x in v if str(x).strip()]
        for k, v in getattr(module, "THEME_MULTI", {}).items()
    }
    return theme, theme_multi


def normalize_stock_id(idx: pd.Index | pd.Series) -> pd.Index:
    return pd.Index(idx.astype(str).str.replace(r"\.0$", "", regex=True).str.strip())


def nearest_row_on_or_after(df: pd.DataFrame, date: pd.Timestamp) -> pd.Series:
    pos = df.index.searchsorted(date)
    if pos >= len(df.index):
        pos = len(df.index) - 1
    return df.iloc[pos]


def nearest_row_on_or_before(df: pd.DataFrame, date: pd.Timestamp) -> pd.Series:
    pos = df.index.searchsorted(date, side="right") - 1
    if pos < 0:
        pos = 0
    return df.iloc[pos]


def build_html(
    out_path: Path,
    latest_date: pd.Timestamp,
    peak_date: pd.Timestamp,
    market_start: float,
    market_end: float,
    market_ret: float,
    theme_summary: pd.DataFrame,
    top_stock_rows: pd.DataFrame,
    top_stock_rows_median: pd.DataFrame,
    sort_mode: str,
    theme_cycle_order: list[str],
    theme_cycle_order_median: list[str],
    dispersion: float = 0.0,
) -> None:
    theme_rank = {t: i + 1 for i, t in enumerate(theme_cycle_order)}
    theme_rank_median = {t: i + 1 for i, t in enumerate(theme_cycle_order_median)}
    combined_cycle_order = list(dict.fromkeys(theme_cycle_order + theme_cycle_order_median))
    combined_cycle_json = json.dumps(combined_cycle_order, ensure_ascii=False)
    theme_color_class = {
        theme: f"theme-color-{i + 1}"
        for i, theme in enumerate(combined_cycle_order)
    }

    theme_rows = []
    for _, row in theme_summary.iterrows():
        theme_str = str(row['theme'])
        cls = f' class="{theme_color_class[theme_str]}"' if theme_str in theme_color_class else ""
        theme_rows.append(
            f"<tr{cls}>"
            f"<td>{escape(theme_str)}</td>"
            f"<td data-sort='{row['avg_ret']:.10f}'>{pct(row['avg_ret'])}</td>"
            f"<td data-sort='{row['median_ret']:.10f}'>{pct(row['median_ret'])}</td>"
            f"<td data-sort='{row['down_ratio']:.10f}'>{pct(row['down_ratio'])}</td>"
            f"<td data-sort='{int(row['count'])}'>{int(row['count'])}</td>"
            f"<td>{money_100m(row['market_cap_sum'])}</td>"
            "</tr>"
        )

    # 合併平均前三 / 中位數前三，去重後標記來源
    _COLS = ["theme", "stock_id", "name", "ret", "start_price", "end_price", "market_cap"]
    _df_avg = top_stock_rows[_COLS].copy(); _df_avg["_src"] = "avg"
    _df_med = top_stock_rows_median[_COLS].copy(); _df_med["_src"] = "med"
    def _agg_src(s: pd.Series) -> str:
        v = set(s)
        return "both" if "avg" in v and "med" in v else s.iloc[0]
    merged_df = (
        pd.concat([_df_avg, _df_med])
        .groupby(["theme", "stock_id"], as_index=False, sort=False)
        .agg(name=("name", "first"), ret=("ret", "first"),
             start_price=("start_price", "first"), end_price=("end_price", "first"),
             market_cap=("market_cap", "first"), _src=("_src", _agg_src))
        .sort_values(["theme", "ret"])
        .reset_index(drop=True)
    )
    _BADGE = {"avg": ("badge-avg", "均"), "med": ("badge-med", "中"), "both": ("badge-both", "均＋中")}
    merged_stock_rows = []
    for _, row in merged_df.iterrows():
        theme_str = str(row["theme"])
        src = row["_src"]
        row_cls = theme_color_class.get(theme_str, "")
        cls = f' class="{row_cls}"' if row_cls else ""
        badge_cls, badge_text = _BADGE[src]
        merged_stock_rows.append(
            f"<tr{cls}>"
            f"<td>{escape(theme_str)}</td>"
            f"<td>{escape(str(row['stock_id']))}</td>"
            f"<td>{escape(str(row['name']))}</td>"
            f"<td data-sort='{row['ret']:.10f}'>{pct(row['ret'])}</td>"
            f"<td data-sort='{row['start_price']:.10f}'>{row['start_price']:,.2f}</td>"
            f"<td data-sort='{row['end_price']:.10f}'>{row['end_price']:,.2f}</td>"
            f"<td data-sort='{row['market_cap']:.2f}'>{money_100m(row['market_cap'])}</td>"
            f'<td class="src-cell"><span class="badge {badge_cls}">{badge_text}</span></td>'
            "</tr>"
        )

    market_diff = market_end - market_start
    meta_ret_cls = "neg" if market_ret < 0 else "pos"
    DISPERSION_THRESHOLD = 0.07
    disp_suitable = dispersion >= DISPERSION_THRESHOLD
    disp_label = "適合「跌最深」策略 ✓" if disp_suitable else "分散度不足，效果可能較弱"
    disp_color = "#0a6b3a" if disp_suitable else "#b45309"
    html = f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<title>大跌後族群跌幅掃描</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans TC", sans-serif; margin: 32px; color: #1f2933; background: #f0f4f8; }}
h1 {{ margin: 0 0 6px; font-size: 28px; font-weight: 800; letter-spacing: -.5px; }}
h2 {{ margin: 32px 0 10px; font-size: 13px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: #627d98; border-bottom: 2px solid #d9e2ec; padding-bottom: 6px; }}
.meta-card {{ display: flex; flex-wrap: wrap; background: white; border: 1px solid #d9e2ec; border-radius: 10px; margin-bottom: 24px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,.06); }}
.meta-item {{ flex: 1; min-width: 160px; padding: 14px 22px; border-right: 1px solid #e4e7eb; }}
.meta-item:last-child {{ border-right: none; }}
.meta-label {{ font-size: 11px; font-weight: 700; letter-spacing: .07em; text-transform: uppercase; color: #829ab1; margin-bottom: 4px; }}
.meta-value {{ font-size: 18px; font-weight: 700; color: #1f2933; }}
table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #d9e2ec; }}
th, td {{ padding: 9px 12px; border-bottom: 1px solid #e4e7eb; text-align: left; white-space: nowrap; }}
th {{ cursor: pointer; user-select: none; background: #f0f4f8; position: sticky; top: 0; font-weight: 600; }}
th:hover {{ background: #e4edf6; }}
td:nth-child(n+4), th:nth-child(n+4) {{ text-align: right; }}
.neg {{ color: #c0392b; }}
.pos {{ color: #0a6b3a; }}
.wrap {{ overflow-x: auto; margin-bottom: 16px; box-shadow: 0 1px 4px rgba(0,0,0,.05); }}
.theme-color-1 {{ background: #fff1f2; }}
.theme-color-2 {{ background: #fff7ed; }}
.theme-color-3 {{ background: #fefce8; }}
.theme-color-4 {{ background: #ecfeff; }}
.theme-color-5 {{ background: #eff6ff; }}
.theme-color-6 {{ background: #f5f3ff; }}
.theme-color-1 td:first-child {{ border-left: 4px solid #fb7185; }}
.theme-color-2 td:first-child {{ border-left: 4px solid #fdba74; }}
.theme-color-3 td:first-child {{ border-left: 4px solid #fde047; }}
.theme-color-4 td:first-child {{ border-left: 4px solid #67e8f9; }}
.theme-color-5 td:first-child {{ border-left: 4px solid #93c5fd; }}
.theme-color-6 td:first-child {{ border-left: 4px solid #c4b5fd; }}
.src-cell {{ text-align: left !important; }}
.badge {{ display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 10px; font-weight: 700; }}
.badge-avg {{ background: #fff1f2; color: #be123c; }}
.badge-med {{ background: #eff6ff; color: #1d4ed8; }}
.badge-both {{ background: #f0fdf4; color: #15803d; }}
.disp-badge {{ display: inline-block; margin-top: 4px; padding: 2px 8px; border-radius: 99px; font-size: 11px; font-weight: 700; background: #f0f4f8; }}
</style>
</head>
<body>
<h1>大跌後族群跌幅掃描</h1>
<div class="meta-card">
  <div class="meta-item">
    <div class="meta-label">大盤區間</div>
    <div class="meta-value"><span style="color:#dc2626">{peak_date.date()}</span> → <span style="color:#16a34a">{latest_date.date()}</span></div>
  </div>
  <div class="meta-item">
    <div class="meta-label">TAIEX</div>
    <div class="meta-value">{market_start:,.0f} → {market_end:,.0f}</div>
  </div>
  <div class="meta-item">
    <div class="meta-label">大盤跌幅</div>
    <div class="meta-value {meta_ret_cls}">{market_diff:+,.0f} 點　{pct(market_ret)}</div>
  </div>
  <div class="meta-item">
    <div class="meta-label">類股分散度（σ）</div>
    <div class="meta-value" style="color:{disp_color}">{dispersion * 100:.2f}%</div>
    <div class="disp-badge" style="color:{disp_color}">{disp_label}</div>
  </div>
</div>

<h2>族群跌幅排序</h2>
<div class="wrap"><table class="sortable">
<thead><tr><th>族群</th><th>平均表現</th><th>中位數</th><th>下跌比例</th><th>股票數</th><th>總市值</th></tr></thead>
<tbody>{''.join(theme_rows)}</tbody>
</table></div>

<h2>前三族群成分股　<small style="font-weight:400;font-size:11px;color:#829ab1">均＝平均前三・中＝中位數前三・均＋中＝兩者皆入選</small></h2>
<div class="wrap"><table class="sortable" id="stocks-table">
<thead><tr><th data-cycle-theme="1">族群</th><th>代號</th><th>名稱</th><th>區間表現</th><th>起始價</th><th>最近價</th><th>市值</th><th>收錄</th></tr></thead>
<tbody>{''.join(merged_stock_rows)}</tbody>
</table></div>

<script>
const themeCycleOrder = {combined_cycle_json};
let themeCycleIndex = -1;
document.querySelectorAll("td").forEach(td => {{
  const n = Number(td.dataset.sort);
  if (!Number.isNaN(n)) td.classList.add(n < 0 ? "neg" : "pos");
}});
document.querySelectorAll("table.sortable th").forEach(th => {{
  th.addEventListener("click", () => {{
    const table = th.closest("table");
    const tbody = table.querySelector("tbody");
    const rows = Array.from(tbody.querySelectorAll("tr"));
    const colIdx = Array.from(th.parentElement.children).indexOf(th);
    if (table.id === "stocks-table" && colIdx === 0) {{
      const themes = themeCycleOrder.length
        ? themeCycleOrder
        : Array.from(new Set(rows.map(r => r.children[0].innerText.trim())));
      if (!themes.length) return;
      themeCycleIndex = (themeCycleIndex + 1) % themes.length;
      const selected = themes[themeCycleIndex];
      table.querySelectorAll("th").forEach(h => {{ h.dataset.asc = ""; }});
      th.textContent = "族群：" + selected + " ↑";
      rows.sort((a, b) => {{
        const aHit = a.children[0].innerText.trim() === selected;
        const bHit = b.children[0].innerText.trim() === selected;
        if (aHit !== bHit) return aHit ? -1 : 1;
        const ar = Number(a.children[3].dataset.sort);
        const br = Number(b.children[3].dataset.sort);
        return ar - br;
      }});
      rows.forEach(r => tbody.appendChild(r));
      return;
    }}
    if (table.id === "stocks-table") {{
      themeCycleIndex = -1;
      const thTh = table.querySelector("th[data-cycle-theme]");
      if (thTh) thTh.textContent = "族群";
    }}
    const asc = th.dataset.asc !== "1";
    table.querySelectorAll("th").forEach(h => {{ h.dataset.asc = ""; }});
    th.dataset.asc = asc ? "1" : "0";
    rows.sort((a, b) => {{
      const av = a.children[colIdx].dataset.sort ?? a.children[colIdx].innerText;
      const bv = b.children[colIdx].dataset.sort ?? b.children[colIdx].innerText;
      const an = Number(av), bn = Number(bv);
      const cmp = Number.isNaN(an) || Number.isNaN(bn) ? String(av).localeCompare(String(bv), "zh-Hant") : an - bn;
      return asc ? cmp : -cmp;
    }});
    rows.forEach(r => tbody.appendChild(r));
  }});
}});
</script>
</body>
</html>"""
    out_path.write_text(html, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="掃描大盤近兩個月高點至最近一日的族群與個股跌幅。")
    parser.add_argument("--research-dir", type=Path, default=DEFAULT_RESEARCH_DIR)
    parser.add_argument("--theme-map", type=Path, default=DEFAULT_THEME_MAP)
    parser.add_argument("--lookback", type=int, default=42, help="近兩個月約 42 個交易日。")
    parser.add_argument("--market-cap-min", type=float, default=50e8, help="市值門檻，預設 50 億。")
    parser.add_argument("--min-theme-count", type=int, default=3, help="族群至少幾檔股票才納入跌幅排名，預設 3。")
    parser.add_argument("--top-themes", type=int, default=3)
    parser.add_argument("--sort", choices=["theme", "performance"], default="performance", help="前三族群個股列表初始排序。")
    parser.add_argument("--output-dir", type=Path, default=SCRIPT_DIR)
    parser.add_argument("--no-html", action="store_true", help="只輸出 CSV，不產生 HTML 報表。")
    parser.add_argument(
        "--sectors",
        nargs="*",
        metavar="SECTOR",
        default=DEFAULT_SECTORS,
        help=(
            "限制掃描範圍的大分類，以空白分隔。"
            f"可選：{', '.join(SECTOR_BROAD_CATS)}。"
            "不傳此參數則套用預設四大類；傳入 --sectors 且不附值則掃描全部族群。"
        ),
    )
    return parser.parse_args()


def main() -> None:
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    args = parse_args()
    load_dotenv(args.research_dir / ".env")

    from finlab import data

    theme_map, theme_multi = load_theme_maps(args.theme_map)
    close = data.get("price:收盤價").copy()
    market_value = data.get("etl:market_value").copy()
    company_info = data.get("company_basic_info").copy()
    taiex = data.get("taiex_total_index:收盤指數").copy()

    close.columns = normalize_stock_id(pd.Series(close.columns))
    market_value.columns = normalize_stock_id(pd.Series(market_value.columns))
    taiex_series = taiex["TAIEX"].dropna()

    market_window = taiex_series.tail(args.lookback)
    peak_date = pd.Timestamp(market_window.idxmax())
    latest_date = pd.Timestamp(taiex_series.index[-1])
    market_start = float(taiex_series.loc[peak_date])
    market_end = float(taiex_series.iloc[-1])
    market_ret = market_end / market_start - 1

    start_prices = nearest_row_on_or_after(close, peak_date)
    end_prices = nearest_row_on_or_before(close, latest_date)
    latest_mcap = nearest_row_on_or_before(market_value, latest_date)

    company_info["stock_id"] = company_info["stock_id"].astype(str).str.strip()
    info = company_info.set_index("stock_id")
    name_col = company_info.columns[2]
    category_col = company_info.columns[3]
    stock_name = info[name_col].astype(str).str.replace(r"股份有限公司|有限公司", "", regex=True).str.strip()
    broad_cat = info[category_col].astype(str)

    rows = pd.DataFrame(
        {
            "start_price": start_prices,
            "end_price": end_prices,
            "market_cap": latest_mcap,
        }
    )
    rows.index = normalize_stock_id(pd.Series(rows.index))
    rows = rows.replace([np.inf, -np.inf], np.nan).dropna(subset=["start_price", "end_price", "market_cap"])
    rows = rows[(rows.index.str.len() == 4) & ~rows.index.str.startswith("0")]
    rows = rows[rows["market_cap"] >= args.market_cap_min].copy()

    # 限制掃描範圍到指定大分類
    if args.sectors:
        allowed_broad_cats: set[str] = set()
        for s in args.sectors:
            allowed_broad_cats |= SECTOR_BROAD_CATS.get(s, {s})
        rows_cats = rows.index.map(lambda sid: broad_cat.get(sid, ""))
        rows = rows[rows_cats.isin(allowed_broad_cats)]
        print(f"族群範圍限制：{', '.join(args.sectors)}  (共 {len(rows)} 檔)")

    rows["ret"] = rows["end_price"] / rows["start_price"] - 1
    rows["name"] = rows.index.map(lambda sid: stock_name.get(sid, sid))
    def map_themes(sid: str) -> list[str]:
        themes = theme_multi.get(sid)
        if themes:
            return list(dict.fromkeys(themes))
        theme = theme_map.get(sid) or BROAD_MAP.get(broad_cat.get(sid, ""), broad_cat.get(sid, ""))
        return [theme] if theme else []

    rows["theme"] = rows.index.map(map_themes)
    rows = rows.explode("theme")
    rows = rows[rows["theme"].fillna("").ne("")]
    rows["stock_id"] = rows.index

    theme_summary = (
        rows.groupby("theme", as_index=False)
        .agg(
            avg_ret=("ret", "mean"),
            median_ret=("ret", "median"),
            down_ratio=("ret", lambda s: float((s < 0).mean())),
            count=("ret", "size"),
            market_cap_sum=("market_cap", "sum"),
        )
        .sort_values(["avg_ret", "median_ret"], ascending=[True, True])
        .reset_index(drop=True)
    )
    ranked_theme_summary = theme_summary[theme_summary["count"] >= args.min_theme_count].copy()
    if ranked_theme_summary.empty:
        ranked_theme_summary = theme_summary.copy()

    # 類股分散度 = 各族群平均報酬的標準差（衡量市場族群輪動強度）
    dispersion = float(ranked_theme_summary["avg_ret"].std()) if len(ranked_theme_summary) > 1 else 0.0

    # 平均數前三
    weakest_themes = ranked_theme_summary.head(args.top_themes)["theme"].tolist()
    top_stock_rows = rows[rows["theme"].isin(weakest_themes)].copy()
    if args.sort == "theme":
        top_stock_rows = top_stock_rows.sort_values(["theme", "ret"], ascending=[True, True])
    else:
        top_stock_rows = top_stock_rows.sort_values(["ret", "theme"], ascending=[True, True])

    # 中位數前三
    ranked_by_median = ranked_theme_summary.sort_values(["median_ret", "avg_ret"], ascending=[True, True])
    weakest_themes_median = ranked_by_median.head(args.top_themes)["theme"].tolist()
    top_stock_rows_median = rows[rows["theme"].isin(weakest_themes_median)].copy()
    if args.sort == "theme":
        top_stock_rows_median = top_stock_rows_median.sort_values(["theme", "ret"], ascending=[True, True])
    else:
        top_stock_rows_median = top_stock_rows_median.sort_values(["ret", "theme"], ascending=[True, True])

    date_tag = latest_date.strftime("%Y-%m-%d")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    theme_csv = args.output_dir / "market_drop_theme_summary.csv"
    stock_csv = args.output_dir / "market_drop_top_theme_stocks.csv"
    ranked_theme_summary.to_csv(theme_csv, index=False, encoding="utf-8-sig")
    top_stock_rows[
        ["theme", "stock_id", "name", "ret", "start_price", "end_price", "market_cap"]
    ].to_csv(stock_csv, index=False, encoding="utf-8-sig")
    html_path = None
    if not args.no_html:
        html_path = args.output_dir / f"market_drop_theme_scan_{date_tag}.html"
        build_html(html_path, latest_date, peak_date, market_start, market_end, market_ret, ranked_theme_summary, top_stock_rows, top_stock_rows_median, args.sort, weakest_themes, weakest_themes_median, dispersion)

    DISPERSION_THRESHOLD = 0.07
    disp_verdict = "適合「跌最深」策略 ✓" if dispersion >= DISPERSION_THRESHOLD else "分散度不足，效果可能較弱"
    print(f"大盤區間: {peak_date.date()} -> {latest_date.date()}")
    print(f"TAIEX: {market_start:,.2f} -> {market_end:,.2f} ({pct(market_ret)})")
    print(f"類股分散度（σ）: {dispersion * 100:.2f}%  ({'>=' if dispersion >= DISPERSION_THRESHOLD else '<'} {DISPERSION_THRESHOLD * 100:.0f}%)  →  {disp_verdict}")
    print("\n跌幅最深族群:")
    print(
        ranked_theme_summary.head(15)
        .assign(
            avg_ret=lambda d: d["avg_ret"].map(pct),
            median_ret=lambda d: d["median_ret"].map(pct),
            down_ratio=lambda d: d["down_ratio"].map(pct),
            market_cap_sum=lambda d: d["market_cap_sum"].map(money_100m),
        )
        .rename(
            columns={
                "theme": "族群",
                "avg_ret": "平均表現",
                "median_ret": "中位數",
                "down_ratio": "下跌比例",
                "count": "股票數",
                "market_cap_sum": "總市值",
            }
        )
        .to_string(index=False)
    )
    _stock_cols = {"theme": "族群", "stock_id": "代號", "name": "名稱", "ret": "區間表現", "start_price": "起始價", "end_price": "最近價", "market_cap": "市值"}
    print(f"\n[平均數] 跌幅最深前三族群成分股（{', '.join(weakest_themes)}）:")
    print(
        top_stock_rows[["theme", "stock_id", "name", "ret", "start_price", "end_price", "market_cap"]]
        .assign(ret=lambda d: d["ret"].map(pct), market_cap=lambda d: d["market_cap"].map(money_100m))
        .rename(columns=_stock_cols)
        .to_string(index=False)
    )
    print(f"\n[中位數] 跌幅最深前三族群成分股（{', '.join(weakest_themes_median)}）:")
    print(
        top_stock_rows_median[["theme", "stock_id", "name", "ret", "start_price", "end_price", "market_cap"]]
        .assign(ret=lambda d: d["ret"].map(pct), market_cap=lambda d: d["market_cap"].map(money_100m))
        .rename(columns=_stock_cols)
        .to_string(index=False)
    )
    print(f"\n輸出: {theme_csv}")
    print(f"輸出: {stock_csv}")
    if html_path:
        print(f"輸出: {html_path}")


if __name__ == "__main__":
    main()
