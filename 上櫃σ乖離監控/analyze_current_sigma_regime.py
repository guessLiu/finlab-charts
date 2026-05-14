import os
import sys
import warnings

sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(raise_error_if_not_found=True, usecwd=False))

import finlab
finlab.login(os.environ["FINLAB_API_TOKEN"])
from finlab import data

import numpy as np
import pandas as pd


MA_PERIODS = [20, 60, 120, 240]
THRESHOLDS = {'MA20': 8.5, 'MA60': 14.5, 'MA120': 17.5, 'MA240': 20.5}
HORIZONS = [20, 60, 120]
MIN_GAP_DAYS = 20


def thin_dates(df, min_gap_days=20):
    kept = []
    last = None
    for dt in df.index:
        if last is None or (dt - last).days >= min_gap_days:
            kept.append(dt)
            last = dt
    return df.loc[kept]


def forward_table(base, horizons=HORIZONS, label=''):
    rows = []
    for h in horizons:
        r = base[f'fwd_{h}d'].dropna()
        rows.append({
            '情境': label,
            '天數': h,
            '樣本數': int(r.size),
            '上漲機率': (r > 0).mean(),
            '下跌機率': (r < 0).mean(),
            '平均報酬': r.mean(),
            '中位數': r.median(),
            '10分位': r.quantile(0.10),
            '25分位': r.quantile(0.25),
            '75分位': r.quantile(0.75),
            '90分位': r.quantile(0.90),
            '跌逾5%機率': (r <= -0.05).mean(),
            '跌逾10%機率': (r <= -0.10).mean(),
            '漲逾5%機率': (r >= 0.05).mean(),
            '漲逾10%機率': (r >= 0.10).mean(),
        })
    return pd.DataFrame(rows)


print("載入上櫃指數...")
mkt = data.get('market_transaction_info:收盤指數')
mkt.index = pd.to_datetime(mkt.index)
otc = mkt['OTC'].dropna().sort_index()
daily_ret = otc.pct_change()

feat = {}
for m in MA_PERIODS:
    ma = otc.rolling(m, min_periods=m).mean()
    pct_dev = (otc - ma) / ma
    roll_std = daily_ret.rolling(m, min_periods=m // 2).std()
    feat[f'MA{m}'] = pct_dev / roll_std

df = pd.DataFrame(feat).dropna()
for h in HORIZONS:
    df[f'fwd_{h}d'] = otc.shift(-h) / otc - 1

keys = [f'MA{m}' for m in MA_PERIODS]
df['avg_sigma'] = df[keys].mean(axis=1)
df['disp_sigma'] = df[keys].std(axis=1)
df['spread_240_20'] = df['MA240'] - df['MA20']
df['ordered_long_hot'] = (
    (df['MA20'] < df['MA60'])
    & (df['MA60'] < df['MA120'])
    & (df['MA120'] < df['MA240'])
)
df['mid_long_over'] = (
    (df['MA120'] > THRESHOLDS['MA120'])
    & (df['MA240'] > THRESHOLDS['MA240'])
)

now = df.dropna(subset=keys).iloc[-1]
hist = df.loc[:now.name - pd.Timedelta(days=120)].dropna(subset=[f'fwd_{h}d' for h in HORIZONS])

avg_q = hist['avg_sigma'].rank(pct=True).loc[hist.index].reindex([now.name])
disp_q = hist['disp_sigma'].rank(pct=True).loc[hist.index].reindex([now.name])

current = {
    'date': now.name,
    'MA20': now['MA20'],
    'MA60': now['MA60'],
    'MA120': now['MA120'],
    'MA240': now['MA240'],
    'avg_sigma': now['avg_sigma'],
    'disp_sigma': now['disp_sigma'],
    'spread_240_20': now['spread_240_20'],
    'avg_percentile': (hist['avg_sigma'] <= now['avg_sigma']).mean(),
    'disp_percentile': (hist['disp_sigma'] <= now['disp_sigma']).mean(),
}

conditions = {
    'A: MA20<MA60<MA120<MA240': hist['ordered_long_hot'],
    'B: MA120與MA240超標': hist['mid_long_over'],
    'C: A且B': hist['ordered_long_hot'] & hist['mid_long_over'],
    'D: C且平均σ/分歧度都在歷史前25%': (
        hist['ordered_long_hot']
        & hist['mid_long_over']
        & (hist['avg_sigma'] >= hist['avg_sigma'].quantile(0.75))
        & (hist['disp_sigma'] >= hist['disp_sigma'].quantile(0.75))
    ),
    'E: 接近目前狀態(平均σ±3, 分歧度±3, MA240-MA20±6)': (
        (hist['avg_sigma'].between(now['avg_sigma'] - 3, now['avg_sigma'] + 3))
        & (hist['disp_sigma'].between(now['disp_sigma'] - 3, now['disp_sigma'] + 3))
        & (hist['spread_240_20'].between(now['spread_240_20'] - 6, now['spread_240_20'] + 6))
    ),
}

tables = []
for label, mask in conditions.items():
    raw = hist[mask]
    thinned = thin_dates(raw, MIN_GAP_DAYS)
    tables.append(forward_table(thinned, label=label))
result = pd.concat(tables, ignore_index=True)

out_dir = os.path.dirname(os.path.abspath(__file__))
out_path = os.path.join(out_dir, 'current_sigma_regime_stats.csv')
result.to_csv(out_path, index=False, encoding='utf-8-sig')

print(f"資料期間：{otc.index[0].date()} ~ {otc.index[-1].date()}")
print(f"最新日：{current['date'].date()}")
print(
    "目前σ："
    f" MA20={current['MA20']:.2f}, MA60={current['MA60']:.2f},"
    f" MA120={current['MA120']:.2f}, MA240={current['MA240']:.2f}"
)
print(
    "目前結構："
    f" 平均σ={current['avg_sigma']:.2f}(歷史百分位 {current['avg_percentile']:.1%}),"
    f" 分歧度={current['disp_sigma']:.2f}(歷史百分位 {current['disp_percentile']:.1%}),"
    f" MA240-MA20={current['spread_240_20']:.2f}"
)

fmt = {
    '上漲機率': '{:.1%}'.format,
    '下跌機率': '{:.1%}'.format,
    '平均報酬': '{:+.2%}'.format,
    '中位數': '{:+.2%}'.format,
    '10分位': '{:+.2%}'.format,
    '25分位': '{:+.2%}'.format,
    '75分位': '{:+.2%}'.format,
    '90分位': '{:+.2%}'.format,
    '跌逾5%機率': '{:.1%}'.format,
    '跌逾10%機率': '{:.1%}'.format,
    '漲逾5%機率': '{:.1%}'.format,
    '漲逾10%機率': '{:.1%}'.format,
}
print("\n條件統計（樣本已用至少20日間隔去重，降低連續日重複）：")
print(result.to_string(index=False, formatters=fmt))
print(f"\n輸出：{out_path}")
