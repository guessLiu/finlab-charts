import sys
sys.stdout.reconfigure(encoding="utf-8")

import json
import os

from dotenv import find_dotenv, load_dotenv
import finlab
from finlab import data
import numpy as np
import pandas as pd


INITIAL_CAPITAL = 1_000_000
START = pd.Timestamp("2009-01-01")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backtest")

HOLD = "HOLD"
CASH = "CASH"


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
    mdd = float(drawdown.min())
    mdd_date = drawdown.idxmin()

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
        "mdd_pct": round(mdd * 100, 2),
        "mdd_date": str(mdd_date.date()),
    }


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


load_dotenv(find_dotenv(raise_error_if_not_found=True, usecwd=False))
finlab.login(os.environ["FINLAB_API_TOKEN"])

price = data.get("etl:adj_close")["0050"].dropna()
margin_balance = data.get("margin_balance:\u878d\u8cc7\u5238\u7e3d\u9918\u984d")
margin = margin_balance["\u4e0a\u5e02\u878d\u8cc7\u4ea4\u6613\u91d1\u984d"].dropna() / 1e8

price_w = price.resample("W").last().dropna()
margin_w = margin.resample("W").last().dropna()
margin_pct_w = margin_w.rolling(104, min_periods=26).rank(pct=True)

common = price_w.index.intersection(margin_pct_w.dropna().index)
common = common[common >= START]

price_w = price_w.loc[common]
margin_pct_w = margin_pct_w.loc[common]
margin_w = margin_w.loc[common]

ma20 = price_w.rolling(20).mean()
below_ma20 = price_w < ma20
below_ma20_3w = below_ma20.rolling(3).sum().eq(3)
above_ma20 = price_w > ma20
hot = margin_pct_w >= 0.80
low_or_depressed = margin_pct_w < 0.40

shares = INITIAL_CAPITAL / price_w.iloc[0]
cash = 0.0
position = HOLD
reentry_armed = False
trades = [{
    "date": str(price_w.index[0].date()),
    "action": "BUY_INITIAL",
    "price": round(float(price_w.iloc[0]), 2),
    "shares": round(float(shares), 6),
    "cash": round(cash, 2),
    "equity": INITIAL_CAPITAL,
    "margin_pct": round(float(margin_pct_w.iloc[0]) * 100, 2),
    "zone": zone_name(float(margin_pct_w.iloc[0])),
}]
rows = []

for date in price_w.index:
    px = float(price_w.loc[date])
    margin_pct = float(margin_pct_w.loc[date])
    event = ""

    if position == HOLD and bool(hot.loc[date]) and bool(below_ma20_3w.loc[date]):
        cash = shares * px
        shares = 0.0
        position = CASH
        reentry_armed = False
        event = "SELL_HOT_AND_3W_BELOW_MA20"
        trades.append({
            "date": str(date.date()),
            "action": "SELL",
            "price": round(px, 2),
            "shares": 0.0,
            "cash": round(cash, 2),
            "equity": round(cash, 2),
            "margin_pct": round(margin_pct * 100, 2),
            "zone": zone_name(margin_pct),
        })
    elif position == CASH:
        if bool(low_or_depressed.loc[date]):
            reentry_armed = True

        if reentry_armed and bool(above_ma20.loc[date]):
            shares = cash / px
            cash = 0.0
            position = HOLD
            reentry_armed = False
            event = "BUY_LOW_OR_DEPRESSED_AND_ABOVE_MA20"
            trades.append({
                "date": str(date.date()),
                "action": "BUY",
                "price": round(px, 2),
                "shares": round(float(shares), 6),
                "cash": 0.0,
                "equity": round(float(shares * px), 2),
                "margin_pct": round(margin_pct * 100, 2),
                "zone": zone_name(margin_pct),
            })

    equity = shares * px + cash
    rows.append({
        "date": date,
        "price": px,
        "ma20": float(ma20.loc[date]) if pd.notna(ma20.loc[date]) else np.nan,
        "margin_amount_100m": float(margin_w.loc[date]),
        "margin_pct": margin_pct,
        "zone": zone_name(margin_pct),
        "hot": bool(hot.loc[date]),
        "low_or_depressed": bool(low_or_depressed.loc[date]),
        "below_ma20_3w": bool(below_ma20_3w.loc[date]),
        "above_ma20": bool(above_ma20.loc[date]),
        "reentry_armed": reentry_armed,
        "position": position,
        "shares": shares,
        "cash": cash,
        "equity": equity,
        "event": event,
    })

result = pd.DataFrame(rows).set_index("date")
strategy_metrics = annualized_metrics(result["equity"])

buy_hold_equity = INITIAL_CAPITAL / price_w.iloc[0] * price_w
buy_hold_metrics = annualized_metrics(buy_hold_equity)

out = {
    "assumptions": {
        "initial_capital": INITIAL_CAPITAL,
        "price": "0050 adjusted weekly close from finlab etl:adj_close",
        "margin_heat": "TWSE margin trading value weekly close, 104-week rolling percentile, hot >= 80%",
        "exit": "hot and 0050 weekly close below weekly MA20 for 3 consecutive weeks",
        "reentry": "after cash, arm reentry when margin percentile is below 40%, then buy when 0050 weekly close is above weekly MA20",
        "costs_taxes_cash_interest": "ignored",
    },
    "strategy": strategy_metrics,
    "buy_and_hold": buy_hold_metrics,
    "exposure_pct": round((result["position"] == HOLD).mean() * 100, 2),
    "trade_count": len(trades),
    "trades": trades,
}

os.makedirs(OUTPUT_DIR, exist_ok=True)
csv_path = os.path.join(OUTPUT_DIR, "backtest_0050_heat_exit_weekly.csv")
json_path = os.path.join(OUTPUT_DIR, "backtest_0050_heat_exit_metrics.json")
result.to_csv(csv_path, encoding="utf-8-sig")
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print(json.dumps(out, ensure_ascii=False, indent=2))
print(f"\nCSV: {csv_path}")
print(f"JSON: {json_path}")
