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
FORWARD_DAYS = 60
STEP = 0.5
MIN_SAMPLES = 30


def first_negative_threshold(stats, field):
    usable = stats[stats['n'] >= MIN_SAMPLES].sort_values('threshold')
    hit = usable[usable[field] <= 0]
    if hit.empty:
        return None
    return float(hit.iloc[0]['threshold'])


print("載入上櫃指數...")
mkt = data.get('market_transaction_info:收盤指數')
mkt.index = pd.to_datetime(mkt.index)
otc = mkt['OTC'].dropna().sort_index()
daily_ret = otc.pct_change()
future_ret = otc.shift(-FORWARD_DAYS) / otc - 1

rows = []
summary = []
for m in MA_PERIODS:
    key = f'MA{m}'
    ma = otc.rolling(m, min_periods=m).mean()
    pct_dev = (otc - ma) / ma
    roll_std = daily_ret.rolling(m, min_periods=m // 2).std()
    sigma = (pct_dev / roll_std).dropna()
    aligned = pd.DataFrame({'sigma': sigma, 'fwd_ret': future_ret}).dropna()

    max_sigma = float(np.floor(aligned['sigma'].max() / STEP) * STEP)
    thresholds = np.arange(0, max_sigma + STEP / 2, STEP)
    stats_rows = []
    for th in thresholds:
        selected = aligned[aligned['sigma'] > th]['fwd_ret']
        if selected.empty:
            continue
        stats_rows.append({
            'ma': key,
            'threshold': round(float(th), 2),
            'n': int(selected.size),
            'mean_60d': float(selected.mean()),
            'median_60d': float(selected.median()),
            'win_rate': float((selected > 0).mean()),
        })
    stats = pd.DataFrame(stats_rows)
    rows.append(stats)

    mean_th = first_negative_threshold(stats, 'mean_60d')
    median_th = first_negative_threshold(stats, 'median_60d')
    summary.append({
        'ma': key,
        'min_samples': MIN_SAMPLES,
        'max_sigma': float(aligned['sigma'].max()),
        'mean_turn_negative': mean_th,
        'median_turn_negative': median_th,
    })

all_stats = pd.concat(rows, ignore_index=True)
summary_df = pd.DataFrame(summary)

out_dir = os.path.dirname(os.path.abspath(__file__))
stats_path = os.path.join(out_dir, 'sigma_threshold_recalibration.csv')
summary_path = os.path.join(out_dir, 'sigma_threshold_summary.csv')
all_stats.to_csv(stats_path, index=False, encoding='utf-8-sig')
summary_df.to_csv(summary_path, index=False, encoding='utf-8-sig')

print(f"資料期間：{otc.index[0].date()} ~ {otc.index[-1].date()}")
print(f"方法：sigma > threshold 後續 {FORWARD_DAYS} 交易日報酬；threshold 每 {STEP} 掃描；至少 {MIN_SAMPLES} 筆")
print("\n主結果：平均報酬首次 <= 0 的 threshold")
print(summary_df.to_string(index=False, formatters={
    'max_sigma': '{:.2f}'.format,
    'mean_turn_negative': lambda x: '無' if pd.isna(x) else f'{x:.1f}',
    'median_turn_negative': lambda x: '無' if pd.isna(x) else f'{x:.1f}',
}))

print("\n各 MA 在主閾值附近的統計：")
for row in summary:
    key = row['ma']
    th = row['mean_turn_negative']
    stats = all_stats[all_stats['ma'] == key]
    if th is None or pd.isna(th):
        view = stats[stats['n'] >= MIN_SAMPLES].tail(5)
    else:
        view = stats[(stats['threshold'] >= th - 1.0) & (stats['threshold'] <= th + 1.0)]
    print(f"\n{key}")
    print(view[['threshold', 'n', 'mean_60d', 'median_60d', 'win_rate']].to_string(
        index=False,
        formatters={
            'threshold': '{:.1f}'.format,
            'mean_60d': '{:+.2%}'.format,
            'median_60d': '{:+.2%}'.format,
            'win_rate': '{:.1%}'.format,
        },
    ))

print(f"\n明細輸出：{stats_path}")
print(f"摘要輸出：{summary_path}")
