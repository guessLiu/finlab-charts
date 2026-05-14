import sys, os
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(raise_error_if_not_found=True, usecwd=False))

import finlab
finlab.login(os.environ["FINLAB_API_TOKEN"])
from finlab import data

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import warnings
warnings.filterwarnings('ignore')

# ── 1. 上櫃指數 ───────────────────────────────────────────────────
print("載入上櫃指數...")
mkt = data.get('market_transaction_info:收盤指數')
mkt.index = pd.to_datetime(mkt.index)
otc = mkt['OTC'].dropna().sort_index()

# ── 2. 計算 4 條均線 σ 乖離 ──────────────────────────────────────
MA_PERIODS = [20, 60, 120, 240]
daily_ret  = otc.pct_change()

feat = {}
for m in MA_PERIODS:
    ma       = otc.rolling(m, min_periods=m).mean()
    pct_dev  = (otc - ma) / ma
    roll_std = daily_ret.rolling(m, min_periods=m // 2).std()
    feat[f'MA{m}'] = pct_dev / roll_std

feat_df = pd.DataFrame(feat).dropna()

# ── 3. 60天期望值轉負閾值（歷史掃描結果） ─────────────────────────
# 方法：對每條均線掃描「bias > X 的所有歷史日後續 60 天中位數報酬」轉負點
THRESHOLDS = {'MA20': 8.5, 'MA60': 14.5, 'MA120': 17.5, 'MA240': 20.5}

COLORS = {
    'MA20':  '#26c6da',
    'MA60':  '#42a5f5',
    'MA120': '#ffa726',
    'MA240': '#ef5350',
}

now_date = feat_df.index[-1]
now_vals = feat_df.iloc[-1]
above    = [ma for ma in THRESHOLDS if now_vals[ma] > THRESHOLDS[ma]]

# ── 3b. 歷史前瞻報酬統計 ──────────────────────────────────────────
BIN_HALF = 1.0  # 以當前 σ ± 1.0 為篩選範圍
FWDS     = [20, 60, 120]

fwd_stats = {}
for _key in ['MA20', 'MA60', 'MA120', 'MA240']:
    _cur  = float(now_vals[_key])
    _mask = (feat_df[_key] >= _cur - BIN_HALF) & (feat_df[_key] <= _cur + BIN_HALF)
    _dates = feat_df.index[_mask]
    _row = {'current': _cur}
    for _fwd in FWDS:
        _rets = []
        for _d in _dates:
            _pos = otc.index.searchsorted(_d)
            _fpos = _pos + _fwd
            if _fpos < len(otc):
                _rets.append((otc.iloc[_fpos] / otc.iloc[_pos] - 1) * 100)
        if _rets:
            _s = pd.Series(_rets)
            _row[_fwd] = dict(n=len(_rets), mean=float(_s.mean()),
                              median=float(_s.median()),
                              best=float(_s.max()), worst=float(_s.min()))
        else:
            _row[_fwd] = None
    fwd_stats[_key] = _row

print(f"資料截至 {now_date.date()}")
for ma in MA_PERIODS:
    key = f'MA{ma}'
    status = '⚠ 超過轉負線' if key in above else '正常'
    print(f"  {key}σ = {now_vals[key]:+.2f}  (轉負線 {THRESHOLDS[key]})  {status}")

# ── 4. 建立三欄圖 ─────────────────────────────────────────────────
fig = make_subplots(
    rows=3, cols=1,
    shared_xaxes=True,
    row_heights=[0.30, 0.48, 0.22],
    vertical_spacing=0.05,
    subplot_titles=[
        '上櫃指數',
        '均線 σ 乖離  （虛線 = 60 天期望值轉負界線）',
        f'歷史前瞻報酬統計  （σ ± {BIN_HALF} 範圍內的歷史日）',
    ],
    specs=[[{"type": "xy"}], [{"type": "xy"}], [{"type": "table"}]],
)

# ── 上欄：OTC 指數 ────────────────────────────────────────────────
fig.add_trace(go.Scatter(
    x=otc.index, y=otc.values,
    mode='lines',
    line=dict(color='#cfd8dc', width=3.0),
    name='上櫃指數',
    hovertemplate='%{x|%Y-%m-%d}  %{y:.2f}<extra>上櫃指數</extra>',
), row=1, col=1)

# 上欄：MA 線（與下欄顏色一致）
ma_series = {}
for m in MA_PERIODS:
    ma_series[m] = otc.rolling(m, min_periods=m).mean()

for m in MA_PERIODS:
    key = f'MA{m}'
    fig.add_trace(go.Scatter(
        x=ma_series[m].index, y=ma_series[m].values,
        mode='lines',
        line=dict(color=COLORS[key], width=1.1),
        name=key,
        hovertemplate=f'%{{x|%Y-%m-%d}}  {key}: %{{y:.2f}}<extra>{key}</extra>',
    ), row=1, col=1)

# 最新點標注
fig.add_trace(go.Scatter(
    x=[now_date], y=[otc.iloc[-1]],
    mode='markers+text',
    marker=dict(color='#ffffff', size=7, symbol='circle'),
    text=[f"  {otc.iloc[-1]:.1f}"],
    textposition='middle right',
    textfont=dict(color='#ffffff', size=11, family='Microsoft JhengHei, Arial'),
    showlegend=False, hoverinfo='skip',
), row=1, col=1)

# 背景標記：各 MA 超過轉負線時，於指數圖以對應顏色淡標
def hex_to_rgba(hex_color, alpha):
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f'rgba({r},{g},{b},{alpha})'

for key in ['MA20', 'MA60', 'MA120', 'MA240']:
    in_danger = feat_df[key] > THRESHOLDS[key]
    danger_idx = in_danger[in_danger].index
    if len(danger_idx) == 0:
        continue
    gaps = np.where(np.diff(danger_idx.view(np.int64)) > pd.Timedelta('5D').value)[0]
    starts = [danger_idx[0]] + [danger_idx[g + 1] for g in gaps]
    ends   = [danger_idx[g] for g in gaps] + [danger_idx[-1]]
    for s, e in zip(starts, ends):
        fig.add_vrect(
            x0=s, x1=e,
            fillcolor=hex_to_rgba(COLORS[key], 0.08),
            line_width=0,
            layer='below',
            row=1, col=1,
        )

# ── 下欄：σ 折線 ─────────────────────────────────────────────────
for key, color in COLORS.items():
    s = feat_df[key]
    fig.add_trace(go.Scatter(
        x=s.index, y=s.values,
        mode='lines',
        line=dict(color=color, width=1.5),
        name=f'{key}σ',
        hovertemplate=f'%{{x|%Y-%m-%d}}  %{{y:+.2f}}σ<extra>{key}</extra>',
    ), row=2, col=1)

# 閾值虛線
for key, thresh in THRESHOLDS.items():
    fig.add_hline(
        y=thresh, row=2, col=1,
        line=dict(color=COLORS[key], width=1.1, dash='dash'),
        annotation_text=f'{key} 轉負 ({thresh}σ)',
        annotation_position='top right',
        annotation_font=dict(size=9.5, color=COLORS[key],
                             family='Microsoft JhengHei, Arial'),
    )

# 當前值菱形
for key, color in COLORS.items():
    fig.add_trace(go.Scatter(
        x=[now_date], y=[now_vals[key]],
        mode='markers',
        marker=dict(color=color, size=9, symbol='diamond'),
        showlegend=False,
        hovertemplate=f'{key}σ 現在: {now_vals[key]:+.2f}<extra></extra>',
    ), row=2, col=1)

# ── 4b. 前瞻報酬統計表 ────────────────────────────────────────────
def _p(v):
    return f'{v:+.1f}%' if v is not None else '–'

_ma_keys = ['MA20', 'MA60', 'MA120', 'MA240']
_header  = ['均線', '今日σ值',
            '20天<br>樣本數', '20天<br>平均報酬', '20天<br>中位報酬', '20天<br>最佳報酬', '20天<br>最差報酬',
            '60天<br>樣本數', '60天<br>平均報酬', '60天<br>中位報酬', '60天<br>最佳報酬', '60天<br>最差報酬',
            '120天<br>樣本數', '120天<br>平均報酬', '120天<br>中位報酬', '120天<br>最佳報酬', '120天<br>最差報酬']
_cells   = [[] for _ in _header]
_cell_colors = [[] for _ in _header]
_GREEN, _RED, _BASE = '#1b3a2a', '#3a1b1b', '#0d1117'

# 三個時間段的主題色：藍 / 紫 / 橘
_GRP_HDR  = {20: '#1a3a5c', 60: '#3c1a5c', 120: '#5c3a1a'}
_GRP_CELL = {20: '#0d1e30', 60: '#1e0d30', 120: '#301a0d'}

for _k in _ma_keys:
    _st = fwd_stats[_k]
    _cells[0].append(_k)
    _cells[1].append(f"{_st['current']:+.2f}σ")
    _cell_colors[0].append(_BASE)
    _cell_colors[1].append(_BASE)
    for _fi, _fwd in enumerate([20, 60, 120]):
        _d    = _st.get(_fwd)
        _base = 2 + _fi * 5
        _bg   = _GRP_CELL[_fwd]
        if _d:
            _vals = [str(_d['n']), _p(_d['mean']), _p(_d['median']),
                     _p(_d['best']), _p(_d['worst'])]
            _cols = [_bg,
                     _GREEN if _d['mean']   >= 0 else _RED,
                     _GREEN if _d['median'] >= 0 else _RED,
                     _GREEN, _RED]
        else:
            _vals = ['–', '–', '–', '–', '–']
            _cols = [_bg] * 5
        for _j, (_v, _c) in enumerate(zip(_vals, _cols)):
            _cells[_base + _j].append(_v)
            _cell_colors[_base + _j].append(_c)

_hdr_colors = [_BASE, _BASE] + [_GRP_HDR[f] for f in [20, 60, 120] for _ in range(5)]
_N_COLS     = len(_header)

fig.add_trace(go.Table(
    columnwidth=[1] * _N_COLS,
    header=dict(
        values=_header,
        fill_color=_hdr_colors,
        font=dict(color='#cfd8dc', size=10, family='Microsoft JhengHei, Arial'),
        align='center',
        line_color='#37474f',
        height=28,
    ),
    cells=dict(
        values=_cells,
        fill_color=_cell_colors,
        font=dict(color='#cfd8dc', size=10, family='Microsoft JhengHei, Arial'),
        align='center',
        line_color='#263238',
        line_width=1,
        height=24,
    ),
), row=3, col=1)

# 平均/中位欄外框：只框 header + 4 筆資料列，避開 table domain 底部空白。
_sp = 0.05
_rh = [0.30, 0.48, 0.22]
_sc = (1.0 - _sp * (len(_rh) - 1)) / sum(_rh)
_py = 1.0
for _ri2, _rhi in enumerate(_rh):
    _rhp = _rhi * _sc
    if _ri2 == len(_rh) - 1:
        _tbl_y0, _tbl_y1 = round(_py - _rhp, 6), round(_py, 6)
    _py -= _rhp + _sp

_TABLE_DOMAIN_HEIGHT = _tbl_y1 - _tbl_y0
_VISIBLE_TABLE_RATIO = 0.87
_frame_y0 = _tbl_y1 - _TABLE_DOMAIN_HEIGHT * _VISIBLE_TABLE_RATIO

for _gs, _ge in [(3, 4), (8, 9), (13, 14)]:
    fig.add_shape(
        type='rect', xref='paper', yref='paper',
        x0=_gs / _N_COLS, y0=_frame_y0,
        x1=(_ge + 1) / _N_COLS, y1=_tbl_y1,
        line=dict(color='#ef5350', width=2),
        fillcolor='rgba(0,0,0,0)',
        layer='above',
    )

# ── 5. 版面 ───────────────────────────────────────────────────────
status_str = '、'.join(above) + ' 已越轉負線' if above else '均未越轉負線'
title_text = (
    f'上櫃指數 均線 σ 乖離 監控圖　'
    f'<span style="font-size:14px;color:#ef5350">'
    f'（{now_date.strftime("%Y-%m-%d")}　{status_str}）</span>'
)

fig.update_layout(
    title=dict(
        text=title_text,
        font=dict(size=17, family='Microsoft JhengHei, Arial'),
        x=0.5,
    ),
    autosize=True,
    hovermode='x unified',
    template='plotly_dark',
    paper_bgcolor='#0d1117',
    plot_bgcolor='#0d1117',
    legend=dict(
        orientation='h', x=0.01, y=-0.02,
        font=dict(size=11, family='Microsoft JhengHei, Arial'),
        bgcolor='rgba(0,0,0,0)',
    ),
    margin=dict(t=68, b=40, l=60, r=24, pad=0),
)

def _date_str(ts):
    return pd.Timestamp(ts).strftime('%Y-%m-%d')

def _index_yaxis_range(start, end):
    vals = []
    for s in [otc, *ma_series.values()]:
        in_range = s.loc[(s.index >= start) & (s.index <= end)].dropna()
        in_range = in_range[in_range > 0]
        if len(in_range):
            vals.append(in_range)
    if not vals:
        return None
    y = pd.concat(vals)
    return [float(np.log10(y.min() * 0.97)), float(np.log10(y.max() * 1.03))]

def _range_button(label, start, end):
    display_end = end + pd.DateOffset(months=3)
    x_range = [_date_str(start), _date_str(display_end)]
    return dict(
        label=label,
        method='relayout',
        args=[{
            'xaxis.range': x_range,
            'xaxis2.range': x_range,
            'yaxis.autorange': False,
            'yaxis.range': _index_yaxis_range(start, end),
        }],
    )

initial_start = otc.index[-1] - pd.DateOffset(years=5)
initial_end = otc.index[-1]
initial_display_end = initial_end + pd.DateOffset(months=3)
all_start = otc.index[0]
all_end = otc.index[-1]

fig.update_layout(
    updatemenus=[dict(
        type='buttons',
        direction='right',
        active=1,
        x=0,
        xanchor='left',
        y=1.045,
        yanchor='top',
        bgcolor='#1E1E2E',
        bordercolor='#444',
        borderwidth=1,
        showactive=True,
        font=dict(color='#CCCCCC', size=11,
                  family='Microsoft JhengHei, Arial'),
        pad=dict(l=0, r=0, t=0, b=0),
        buttons=[
            _range_button('3年', otc.index[-1] - pd.DateOffset(years=3), initial_end),
            _range_button('5年', initial_start, initial_end),
            _range_button('10年', otc.index[-1] - pd.DateOffset(years=10), initial_end),
            _range_button('全部', all_start, all_end),
        ],
    )],
    xaxis=dict(
        type='date',
        rangeslider=dict(visible=False),
        range=[_date_str(initial_start), _date_str(initial_display_end)],
        autorange=False,
    ),
    xaxis2=dict(
        range=[_date_str(initial_start), _date_str(initial_display_end)],
        autorange=False,
    ),
    yaxis=dict(
        autorange=False,
        range=_index_yaxis_range(initial_start, initial_end),
    ),
)
fig.update_xaxes(showgrid=True, gridcolor='rgba(255,255,255,0.05)')
fig.update_yaxes(showgrid=True, gridcolor='rgba(255,255,255,0.05)')
fig.update_yaxes(type='log', title_text='上櫃指數（log）', row=1, col=1,
                 title_font=dict(size=11))
fig.update_yaxes(title_text='σ 乖離值', row=2, col=1,
                 title_font=dict(size=11))

# 狀態框
summary_lines = []
for key in ['MA20', 'MA60', 'MA120', 'MA240']:
    flag = ' ⚠' if key in above else ''
    summary_lines.append(
        f"<span style='color:{COLORS[key]}'>{key}σ = {now_vals[key]:+.1f}"
        f"  /  轉負線 {THRESHOLDS[key]}{flag}</span>"
    )
fig.add_annotation(
    xref='paper', yref='paper', x=0.002, y=0.595,
    text='<br>'.join(summary_lines),
    showarrow=False, align='left',
    font=dict(size=11, family='Microsoft JhengHei, Arial'),
    bgcolor='rgba(13,17,23,0.80)',
    bordercolor='#37474f', borderwidth=1, borderpad=7,
)

# ── 6. 輸出（後處理：全滿版 + 按鈕 active 字色修正） ───────────────
script_dir = os.path.dirname(os.path.abspath(__file__))
out_path   = os.path.join(script_dir, 'otc_sigma_monitor.html')
fig.write_html(out_path, include_plotlyjs=True)

# 注入 CSS：100vw × 100vh 無留白，選取按鈕字色固定白色
inject_css = """<style>
  html, body { margin: 0; padding: 0; background: #0d1117; }
  .plotly-graph-div { width: 100vw !important; height: 100vh !important; }
  .updatemenu-container .updatemenu-button rect,
  .updatemenu-container .updatemenu-item-rect {
    fill: #222936 !important;
    stroke: #4b5563 !important;
  }
  .updatemenu-container .updatemenu-button:hover rect,
  .updatemenu-container .updatemenu-button:hover .updatemenu-item-rect {
    fill: #343b49 !important;
  }
  .updatemenu-container text {
    fill: #f3f4f6 !important;
  }
  .hoverlayer .hovertext {
    transform: translateX(320px) !important;
  }
</style>"""

inject_js = """<script>
window.addEventListener('load', function() {
  var gd = document.querySelector('.js-plotly-plot');
  if (!gd) return;

  var HOVER_DX = 320;
  var HOVER_DY = 0;
  var scheduled = false;

  function shiftHoverLabels() {
    scheduled = false;
    document.querySelectorAll('.hoverlayer .hovertext').forEach(function(el) {
      var current = el.getAttribute('transform') || '';
      var shiftedBefore = el.getAttribute('data-shifted-transform');
      var base = current === shiftedBefore
        ? (el.getAttribute('data-base-transform') || current)
        : current;
      var shifted = base.replace(
        /translate\\(([-0-9.]+)(?:,|\\s+)\\s*([-0-9.]+)\\)/,
        function(_, x, y) {
          return 'translate(' + (parseFloat(x) + HOVER_DX) + ',' + (parseFloat(y) + HOVER_DY) + ')';
        }
      );
      if (shifted === base) return;
      el.setAttribute('data-base-transform', base);
      el.setAttribute('data-shifted-transform', shifted);
      el.setAttribute('transform', shifted);
    });
  }

  function scheduleShift() {
    if (scheduled) return;
    scheduled = true;
    window.requestAnimationFrame(shiftHoverLabels);
  }

  gd.on('plotly_hover', scheduleShift);
  gd.addEventListener('mousemove', scheduleShift);

  var hoverLayer = document.querySelector('.hoverlayer');
  if (hoverLayer) {
    new MutationObserver(scheduleShift).observe(hoverLayer, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['transform']
    });
  }

});
</script>"""

import re as _re
with open(out_path, 'r', encoding='utf-8') as f:
    html = f.read()
html = html.replace('<head>', '<head>\n' + inject_css, 1)
html = html.replace('</body>', inject_js + '\n</body>', 1)
html = _re.sub(r'\s+integrity="[^"]*"', '', html)
html = _re.sub(r'\s+crossorigin="[^"]*"', '', html)
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(html)

print(f'\n存檔完成：{out_path}')
