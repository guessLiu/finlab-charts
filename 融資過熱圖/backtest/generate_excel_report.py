import sys
sys.stdout.reconfigure(encoding="utf-8")

import os

from dotenv import find_dotenv, load_dotenv
import finlab
from finlab import data
import numpy as np
import pandas as pd


INITIAL_CAPITAL = 1_000_000
START = pd.Timestamp("2009-01-01")
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
EXCEL_PATH = os.path.join(OUTPUT_DIR, "0050_margin_heat_backtest_report.xlsx")


VARIANTS = [
    {
        "id": "buy_hold",
        "name": "買進持有",
        "exit_rule": "無",
        "reentry_rule": "無",
        "description": "2009-01-04 起投入 100 萬買進 0050，持有到期末。",
    },
    {
        "id": "low40_immediate",
        "name": "過熱轉弱賣出；偏低/低迷立即買回",
        "exit_rule": "融資百分位 >= 80%，且 0050 週收盤連續 3 週低於週 20MA",
        "reentry_rule": "空手後，融資百分位第一次 < 40% 時買回",
        "description": "第一版策略。買回不看價格，只要第一次進入偏低或低迷就買回。",
    },
    {
        "id": "low40_above_ma20",
        "name": "過熱轉弱賣出；偏低/低迷後站上週20MA買回",
        "exit_rule": "融資百分位 >= 80%，且 0050 週收盤連續 3 週低於週 20MA",
        "reentry_rule": "空手後，先等融資百分位 < 40%，再等 0050 週收盤 > 週20MA 買回",
        "description": "目前主腳本版本。買回增加價格轉強濾網。",
    },
    {
        "id": "depressed20_immediate",
        "name": "過熱轉弱賣出；低迷立即買回",
        "exit_rule": "融資百分位 >= 80%，且 0050 週收盤連續 3 週低於週 20MA",
        "reentry_rule": "空手後，融資百分位第一次 < 20% 時買回",
        "description": "只在低迷區買回，不要求價格站上週20MA。",
    },
]


def zone_name(p: float) -> str:
    if p >= 0.80:
        return "hot"
    if p >= 0.60:
        return "high"
    if p >= 0.40:
        return "neutral"
    if p >= 0.20:
        return "low"
    return "depressed"


def annualized_metrics(equity: pd.Series) -> dict:
    equity = equity.dropna()
    rets = equity.pct_change().dropna()
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    final_value = float(equity.iloc[-1])
    total_return = final_value / INITIAL_CAPITAL - 1
    cagr = (final_value / INITIAL_CAPITAL) ** (1 / years) - 1
    ann_ret = rets.mean() * 52
    ann_vol = rets.std() * np.sqrt(52)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else np.nan
    drawdown = equity / equity.cummax() - 1

    return {
        "start": str(equity.index[0].date()),
        "end": str(equity.index[-1].date()),
        "years": round(years, 2),
        "final_value": round(final_value, 2),
        "total_return_pct": round(total_return * 100, 2),
        "cagr_pct": round(cagr * 100, 2),
        "ann_return_pct_arithmetic": round(ann_ret * 100, 2),
        "ann_vol_pct": round(ann_vol * 100, 2),
        "sharpe": round(float(sharpe), 4),
        "mdd_pct": round(float(drawdown.min()) * 100, 2),
        "mdd_date": str(drawdown.idxmin().date()),
    }


def load_weekly_data() -> pd.DataFrame:
    price = data.get("etl:adj_close")["0050"].dropna()
    margin_balance = data.get("margin_balance:\u878d\u8cc7\u5238\u7e3d\u9918\u984d")
    margin = margin_balance["\u4e0a\u5e02\u878d\u8cc7\u4ea4\u6613\u91d1\u984d"].dropna() / 1e8

    price_w = price.resample("W").last().dropna()
    margin_w = margin.resample("W").last().dropna()
    margin_pct_w = margin_w.rolling(104, min_periods=26).rank(pct=True)

    common = price_w.index.intersection(margin_pct_w.dropna().index)
    common = common[common >= START]

    df = pd.DataFrame({
        "price": price_w.loc[common],
        "margin_amount_100m": margin_w.loc[common],
        "margin_pct": margin_pct_w.loc[common],
    })
    df["ma20"] = df["price"].rolling(20).mean()
    df["zone"] = df["margin_pct"].map(zone_name)
    df["hot"] = df["margin_pct"] >= 0.80
    df["low40"] = df["margin_pct"] < 0.40
    df["depressed20"] = df["margin_pct"] < 0.20
    df["above_ma20"] = df["price"] > df["ma20"]
    df["below_ma20_3w"] = (df["price"] < df["ma20"]).rolling(3).sum().eq(3)
    return df


def run_variant(base: pd.DataFrame, variant_id: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    trades = []
    first_date = base.index[0]
    shares = INITIAL_CAPITAL / float(base.loc[first_date, "price"])
    cash = 0.0
    position = "HOLD"
    reentry_armed = False

    trades.append({
        "date": first_date,
        "action": "BUY_INITIAL",
        "price": float(base.loc[first_date, "price"]),
        "equity": INITIAL_CAPITAL,
        "margin_pct": float(base.loc[first_date, "margin_pct"]),
        "zone": base.loc[first_date, "zone"],
    })

    if variant_id == "buy_hold":
        for date, row in base.iterrows():
            rows.append({
                "date": date,
                "position": "HOLD",
                "shares": shares,
                "cash": 0.0,
                "equity": shares * float(row["price"]),
                "event": "",
            })
        return pd.DataFrame(rows).set_index("date"), pd.DataFrame(trades)

    for date, row in base.iterrows():
        price = float(row["price"])
        event = ""

        if position == "HOLD" and bool(row["hot"]) and bool(row["below_ma20_3w"]):
            cash = shares * price
            shares = 0.0
            position = "CASH"
            reentry_armed = False
            event = "SELL"
            trades.append({
                "date": date,
                "action": "SELL",
                "price": price,
                "equity": cash,
                "margin_pct": float(row["margin_pct"]),
                "zone": row["zone"],
            })
        elif position == "CASH":
            if variant_id == "low40_immediate":
                buy_signal = bool(row["low40"]) and not bool(base["low40"].shift(1, fill_value=False).loc[date])
            elif variant_id == "depressed20_immediate":
                buy_signal = bool(row["depressed20"]) and not bool(base["depressed20"].shift(1, fill_value=False).loc[date])
            elif variant_id == "low40_above_ma20":
                if bool(row["low40"]):
                    reentry_armed = True
                buy_signal = reentry_armed and bool(row["above_ma20"])
            else:
                raise ValueError(f"Unknown variant: {variant_id}")

            if buy_signal:
                shares = cash / price
                cash = 0.0
                position = "HOLD"
                reentry_armed = False
                event = "BUY"
                trades.append({
                    "date": date,
                    "action": "BUY",
                    "price": price,
                    "equity": shares * price,
                    "margin_pct": float(row["margin_pct"]),
                    "zone": row["zone"],
                })

        rows.append({
            "date": date,
            "position": position,
            "shares": shares,
            "cash": cash,
            "equity": shares * price + cash,
            "event": event,
            "reentry_armed": reentry_armed,
        })

    return pd.DataFrame(rows).set_index("date"), pd.DataFrame(trades)


def autosize_columns(writer: pd.ExcelWriter) -> None:
    for sheet_name, worksheet in writer.sheets.items():
        df = writer.book[sheet_name]
        for col in df.columns:
            max_len = 0
            col_letter = col[0].column_letter
            for cell in col:
                value = "" if cell.value is None else str(cell.value)
                max_len = max(max_len, len(value))
            worksheet.column_dimensions[col_letter].width = min(max(max_len + 2, 10), 60)


load_dotenv(find_dotenv(raise_error_if_not_found=True, usecwd=False))
finlab.login(os.environ["FINLAB_API_TOKEN"])

base = load_weekly_data()
summary_rows = []
condition_rows = []
all_trades = []
weekly = base.copy()

for variant in VARIANTS:
    result, trades = run_variant(base, variant["id"])
    m = annualized_metrics(result["equity"])
    summary_rows.append({
        "variant_id": variant["id"],
        "strategy": variant["name"],
        **m,
        "exposure_pct": round((result["position"] == "HOLD").mean() * 100, 2),
        "trade_count": len(trades),
    })
    condition_rows.append(variant)

    trades = trades.copy()
    trades.insert(0, "variant_id", variant["id"])
    trades.insert(1, "strategy", variant["name"])
    all_trades.append(trades)

    weekly[f"{variant['id']}_equity"] = result["equity"]
    weekly[f"{variant['id']}_position"] = result["position"]
    weekly[f"{variant['id']}_event"] = result["event"]

summary_df = pd.DataFrame(summary_rows)
conditions_df = pd.DataFrame(condition_rows)
trades_df = pd.concat(all_trades, ignore_index=True)
weekly_out = weekly.reset_index().rename(columns={"index": "date"})

with pd.ExcelWriter(EXCEL_PATH, engine="openpyxl", datetime_format="yyyy-mm-dd") as writer:
    summary_df.to_excel(writer, sheet_name="summary", index=False)
    conditions_df.to_excel(writer, sheet_name="conditions", index=False)
    trades_df.to_excel(writer, sheet_name="trades", index=False)
    weekly_out.to_excel(writer, sheet_name="weekly_data", index=False)
    autosize_columns(writer)

print(EXCEL_PATH)
