# -*- coding: utf-8 -*-
"""
台灣景氣對策燈號 — Interactive Plotly HTML Chart
Output: index.html  (same directory as this script)
"""

import sys, os
sys.path.insert(0, r'C:\Users\Liu Family\Finlab\research')

from dotenv import load_dotenv
load_dotenv(r'C:\Users\Liu Family\Finlab\research\.env')

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from finlab import data

# ── 1. Fetch & clean data ──────────────────────────────────────────────────────
print("Fetching data...")
score_raw = data.get('tw_business_indicators:景氣對策信號(分)').iloc[:, 0].dropna()
stock_raw = data.get('tw_business_indicators_details:股價指數(Index 1966=100)').iloc[:, 0].dropna()

def clean_27(s, start='1985-01-01'):
    """Keep day-27 entries only (consistent provisional series, no spike)."""
    s = s[s.index.day == 27]
    s = s[~s.index.duplicated(keep='last')].sort_index()
    return s[s.index >= start]

score = clean_27(score_raw)
stock = clean_27(stock_raw)

# ── 2. Moving averages ────────────────────────────────────────────────────────
ma3  = score.rolling(3,  min_periods=2).mean()
ma12 = score.rolling(12, min_periods=6).mean()

# ── 3. Zone definitions ────────────────────────────────────────────────────────
zones = [
    ( 9, 16, '#0d47a1', 'rgba(13,71,161,0.18)',   '藍燈 (9-16分)'),
    (17, 22, '#00c6fb', 'rgba(0,198,251,0.18)',   '黃藍燈 (17-22分)'),
    (23, 31, '#43e97b', 'rgba(67,233,123,0.18)',  '綠燈 (23-31分)'),
    (32, 37, '#fa8231', 'rgba(250,130,49,0.18)',  '黃紅燈 (32-37分)'),
    (38, 45, '#e84118', 'rgba(232,65,24,0.18)',   '紅燈 (38-45分)'),
]

def zone_color(val):
    for lo, hi, color, *_ in zones:
        if lo <= val <= hi:
            return color
    return '#aaaaaa'

# ── 4. Group consecutive same-zone points ─────────────────────────────────────
point_colors = [zone_color(v) for v in score.values]
groups = []
cur_color, cur_start = point_colors[0], 0
for i in range(1, len(point_colors)):
    if point_colors[i] != cur_color:
        groups.append((cur_start, i, cur_color))
        cur_start, cur_color = i, point_colors[i]
groups.append((cur_start, len(point_colors), cur_color))

# ── 5. Build figure ────────────────────────────────────────────────────────────
fig = make_subplots(specs=[[{"secondary_y": True}]])
BG = '#0d1117'

# Background zone bands
for lo, hi, _, fill_color, _ in zones:
    fig.add_shape(
        type="rect",
        xref="paper", x0=0, x1=1,
        yref="y2",    y0=lo, y1=hi,
        fillcolor=fill_color, line_width=0, layer="below"
    )

zone_legendrank = {lbl: rank for rank, (_, _, _, _, lbl) in enumerate(zones, start=2)}

# 股價指數 — dashed line + fill, LEFT axis
fig.add_trace(
    go.Scatter(
        x=stock.index, y=stock.values,
        mode='lines',
        fill='tozeroy',
        fillcolor='rgba(255,165,0,0.10)',
        line=dict(color='#ffa502', width=1.6, dash='dot'),
        name='股價指數 (1966=100)',
        legendrank=1,
        hovertemplate='%{x|%Y-%m-%d}<br>股價指數: %{y:,.0f}<extra></extra>'
    ),
    secondary_y=False
)

# Colored score line — RIGHT axis
added_legend = set()
for seg_start, seg_end, color in groups:
    t0 = max(0, seg_start - 1)
    t1 = min(len(score), seg_end + 1)
    zone_name = next((lbl for lo, hi, c, _, lbl in zones if c == color), '景氣信號')
    show_leg  = zone_name not in added_legend
    if show_leg:
        added_legend.add(zone_name)
    fig.add_trace(
        go.Scatter(
            x=score.index[t0:t1], y=score.values[t0:t1],
            mode='lines',
            line=dict(color=color, width=5.0),
            name=zone_name, legendgroup=zone_name, showlegend=show_leg,
            legendrank=zone_legendrank.get(zone_name, 99),
            hovertemplate='%{x|%Y-%m-%d}<br>景氣信號: %{y:.0f} 分<extra></extra>'
        ),
        secondary_y=True
    )

# MA3 — white solid line
fig.add_trace(
    go.Scatter(
        x=ma3.index, y=ma3.values, mode='lines',
        line=dict(color='#ffffff', width=1.8),
        name='MA3 (3期均線)',
        legendrank=7,
        hovertemplate='%{x|%Y-%m-%d}<br>MA3: %{y:.1f}<extra></extra>'
    ),
    secondary_y=True
)

# MA12 — dark purple solid line
fig.add_trace(
    go.Scatter(
        x=ma12.index, y=ma12.values, mode='lines',
        line=dict(color='#9b59b6', width=2.2),
        name='MA12 (12期均線)',
        legendrank=8,
        hovertemplate='%{x|%Y-%m-%d}<br>MA12: %{y:.1f}<extra></extra>'
    ),
    secondary_y=True
)

# Latest dot
latest_date  = score.index[-1]
latest_score = score.iloc[-1]
latest_color = zone_color(latest_score)
latest_label = next((lbl for lo, hi, c, _, lbl in zones if c == latest_color), '')

fig.add_trace(
    go.Scatter(
        x=[latest_date], y=[latest_score],
        mode='markers',
        marker=dict(color='white', size=11, symbol='circle',
                    line=dict(color=latest_color, width=2.5)),
        name='最新值', showlegend=False,
        hovertemplate=f'景氣信號: {latest_score:.0f} 分<extra></extra>'
    ),
    secondary_y=True
)

# ── 6. Time range button dates ────────────────────────────────────────────────
latest_str   = latest_date.strftime('%Y-%m-%d')
d_5yr  = (latest_date - pd.DateOffset(years=5)).strftime('%Y-%m-%d')
d_10yr = (latest_date - pd.DateOffset(years=10)).strftime('%Y-%m-%d')
d_all  = score.index[0].strftime('%Y-%m-%d')

range_buttons = [
    dict(label='5年',  method='relayout',
         args=[{'xaxis.range': [d_5yr,  latest_str], 'xaxis.autorange': False}]),
    dict(label='10年', method='relayout',
         args=[{'xaxis.range': [d_10yr, latest_str], 'xaxis.autorange': False}]),
    dict(label='全部', method='relayout',
         args=[{'xaxis.range': [d_all,  latest_str], 'xaxis.autorange': False}]),
]

# ── 7. Layout ─────────────────────────────────────────────────────────────────
fig.update_layout(
    paper_bgcolor=BG,
    plot_bgcolor=BG,
    font=dict(family='Microsoft JhengHei, Noto Sans TC, sans-serif', color='#c9d1d9'),

    # No native title — we use an annotation instead (avoids overlap with buttons)
    title=None,

    hovermode='x unified',
    hoverlabel=dict(bgcolor='#161b22', bordercolor='#30363d', font_color='white'),

    # Legend — horizontal bar below chart
    legend=dict(
        bgcolor='rgba(22,27,34,0.88)', bordercolor='#30363d', borderwidth=1,
        orientation='h',
        x=0.5, y=-0.15,
        xanchor='center', yanchor='top',
        font=dict(size=11),
        tracegroupgap=0,
        itemsizing='constant'
    ),

    # Range buttons — LEFT side, top
    updatemenus=[dict(
        type='buttons',
        direction='right',
        x=0.0, xanchor='left',
        y=1.0, yanchor='bottom',
        pad=dict(r=0, t=4),
        showactive=True,
        active=0,          # default: 5年
        bgcolor='#161b22',
        bordercolor='#444',
        font=dict(color='#c9d1d9', size=12,
                  family='Microsoft JhengHei, Noto Sans TC, sans-serif'),
        buttons=range_buttons
    )],

    margin=dict(l=65, r=75, t=100, b=140),

    xaxis=dict(
        showgrid=True, gridcolor='#21262d', gridwidth=0.5,
        linecolor='#30363d', tickcolor='#30363d',
        tickfont=dict(color='#8b949e', size=10),
        rangeslider=dict(
            visible=True,
            bgcolor='#161b22',
            bordercolor='#30363d',
            thickness=0.04
        ),
        range=[d_5yr, latest_str],
        type='date'
    ),

    yaxis=dict(
        title=dict(text='股價指數 (1966=100)', font=dict(color='#8b949e', size=10)),
        showgrid=True, gridcolor='#21262d', gridwidth=0.5,
        linecolor='#30363d', tickcolor='#30363d',
        tickfont=dict(color='#8b949e', size=10),
        tickformat=',.0f',
        autorange=True,
    ),

    yaxis2=dict(
        title=dict(text='景氣對策信號 (分)', font=dict(color='#8b949e', size=10)),
        showgrid=False,
        linecolor='#30363d', tickcolor='#30363d',
        tickfont=dict(color='#8b949e', size=10),
        range=[5, 50], fixedrange=True,
        side='right', overlaying='y'
    ),
)

# ── 8. Annotations ────────────────────────────────────────────────────────────

# Chart title — centered above plot, large font
fig.add_annotation(
    text='<b>台灣景氣對策燈號</b>',
    xref='paper', yref='paper',
    x=0.5, y=1.10,
    showarrow=False,
    font=dict(size=26, color='white',
              family='Microsoft JhengHei, Noto Sans TC, sans-serif'),
    xanchor='center', yanchor='bottom'
)

# LATEST block — top-left inside chart, stacked vertically
fig.add_annotation(
    text='LATEST',
    xref='paper', yref='paper',
    x=0.01, y=0.99,
    showarrow=False,
    font=dict(size=10, color='#8b949e'),
    xanchor='left', yanchor='top', align='left'
)
fig.add_annotation(
    text=f'<b>{latest_score:.2f}</b>',
    xref='paper', yref='paper',
    x=0.01, y=0.93,
    showarrow=False,
    font=dict(size=28, color='white'),
    xanchor='left', yanchor='top', align='left'
)
fig.add_annotation(
    text=f'<span style="color:{latest_color}">● {latest_label}</span>',
    xref='paper', yref='paper',
    x=0.01, y=0.85,
    showarrow=False,
    font=dict(size=12, family='Microsoft JhengHei, Noto Sans TC, sans-serif'),
    xanchor='left', yanchor='top', align='left'
)
fig.add_annotation(
    text=f'AS OF {latest_date.strftime("%Y/%m/%d")}',
    xref='paper', yref='paper',
    x=0.01, y=0.79,
    showarrow=False,
    font=dict(size=10, color='#8b949e'),
    xanchor='left', yanchor='top', align='left'
)

# ── 9. Save HTML ───────────────────────────────────────────────────────────────
OUT_DIR  = os.path.dirname(os.path.abspath(__file__))
out_html = os.path.join(OUT_DIR, 'index.html')

fig.write_html(
    out_html,
    include_plotlyjs='cdn',
    config={
        'displayModeBar': True,
        'modeBarButtonsToRemove': ['lasso2d', 'select2d'],
        'scrollZoom': True,
        'locale': 'zh-TW'
    }
)
print(f"Done → {out_html}")
