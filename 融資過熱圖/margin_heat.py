import sys
sys.stdout.reconfigure(encoding='utf-8')
import os
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(raise_error_if_not_found=True, usecwd=False))
import finlab
finlab.login(os.environ["FINLAB_API_TOKEN"])
from finlab import data
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ── 資料載入 ──────────────────────────────────────────
taiex = data.get("taiex_total_index:收盤指數")["TAIEX"].dropna()
mb = data.get("margin_balance:融資券總餘額")
margin = mb["上市融資交易金額"] / 1e8

taiex_full  = taiex.resample("W").last().dropna()
margin_full = margin.resample("W").last().dropna()
idx_full = taiex_full.index.intersection(margin_full.index)
taiex_full  = taiex_full.loc[idx_full]
margin_full = margin_full.loc[idx_full]

# ── 1. 2年滾動百分位數 ─────────────────────────────────
margin_pct_full = margin_full.rolling(104, min_periods=26).rank(pct=True)

START = pd.Timestamp("2009-01-01")
taiex_w    = taiex_full[taiex_full.index >= START]
margin_w   = margin_full[margin_full.index >= START]
margin_pct = margin_pct_full[margin_pct_full.index >= START]
mom4       = margin_w.pct_change(4) * 100

# ── 2. 定義區間 ───────────────────────────────────────
def zone(p):
    if   p >= 0.80: return "過熱 (≥80%)"
    elif p >= 0.60: return "偏高 (60-80%)"
    elif p >= 0.40: return "中性 (40-60%)"
    elif p >= 0.20: return "偏低 (20-40%)"
    else:           return "低迷 (<20%)"

margin_zone = margin_pct.map(zone)

# ── 3. 前瞻報酬 ───────────────────────────────────────
HORIZONS = {4: "1個月後", 8: "2個月後", 13: "3個月後", 26: "半年後"}
fwd_returns = {}
for h, label in HORIZONS.items():
    fwd_returns[label] = taiex_w.pct_change(h).shift(-h) * 100

df_zones = pd.DataFrame({
    "margin": margin_w, "margin_pct": margin_pct, "zone": margin_zone
}).dropna()

df = pd.DataFrame({
    "margin": margin_w, "margin_pct": margin_pct, "zone": margin_zone,
    **fwd_returns
}).dropna()

# 百分位方向：與上週相比是上升還是下降
df["pct_dir"] = margin_pct.diff().map(
    lambda x: "↑上升" if pd.notna(x) and x > 0 else "↓下降"
)

# ── 4. 統計輸出 ───────────────────────────────────────
zone_order = ["過熱 (≥80%)", "偏高 (60-80%)", "中性 (40-60%)", "偏低 (20-40%)", "低迷 (<20%)"]
STATS = ["mean", "50%", "std", "25%", "75%", "min", "max"]
STAT_LABELS = {"mean": "均值", "50%": "中位數", "std": "標準差",
               "25%": "Q1(25%)", "75%": "Q3(75%)", "min": "最小值", "max": "最大值"}

for z in zone_order:
    sub = df[df["zone"] == z]
    n = len(sub)
    desc = sub[list(HORIZONS.values())].describe()
    print(f"\n{'='*72}")
    print(f"  {z}　（樣本數：{n} 週）")
    print(f"{'='*72}")
    hdr = f"  {'統計量':<9}"
    for label in HORIZONS.values():
        hdr += f"  {label:>9}"
    print(hdr)
    print(f"  {'-'*65}")
    for s in STATS:
        row = f"  {STAT_LABELS[s]:<9}"
        for label in HORIZONS.values():
            row += f"  {desc.loc[s, label]:>+8.1f}%"
        print(row)
    row_sr = f"  {'夏普比':<9}"
    for label in HORIZONS.values():
        sr_val = sub[label].mean() / sub[label].std()
        row_sr += f"  {sr_val:>+8.2f} "
    print(row_sr)

# 小結論
print(f"\n{'='*72}")
print("【小結論】")
print(f"{'='*72}")
hot   = df[df["zone"] == "過熱 (≥80%)"]
low   = df[df["zone"] == "低迷 (<20%)"]
for label in HORIZONS.values():
    h_med = hot[label].median();  l_med = low[label].median()
    h_std = hot[label].std();     l_std = low[label].std()
    h_sr = hot[label].mean() / hot[label].std()
    l_sr = low[label].mean() / low[label].std()
    print(f"\n  {label}：")
    print(f"    過熱 中位數 {h_med:+.1f}%  均值 {hot[label].mean():+.1f}%  σ={h_std:.1f}%  夏普比={h_sr:+.2f}")
    print(f"    低迷 中位數 {l_med:+.1f}%  均值 {low[label].mean():+.1f}%  σ={l_std:.1f}%  夏普比={l_sr:+.2f}")
    print(f"    → 中位數差距 {l_med-h_med:+.1f}%，波動差 σ {l_std-h_std:+.1f}%")
print(f"\n  ★ 核心發現（2009-2026，週資料）")
h1 = hot["1個月後"].median(); l1 = low["1個月後"].median()
h6 = hot["半年後"].median();  l6 = low["半年後"].median()
print(f"    1個月：過熱 {h1:+.1f}% vs 低迷 {l1:+.1f}%，差距 {l1-h1:.1f} ppt")
print(f"    半年後：過熱 {h6:+.1f}% vs 低迷 {l6:+.1f}%，差距 {l6-h6:.1f} ppt")
print(f"    過熱期標準差顯著高於低迷期（波動放大），夏普比也較低")
print(f"    融資百分位是報酬的反向指標，但短期訊號微弱，半年效果更明顯")

# ── 方向分析：偏高/中性 × 上升 vs 下降 ─────────────────
print(f"\n{'='*72}")
print("【方向分析：相同區間，百分位上升 vs 下降的差異】")
print(f"{'='*72}")
for z in ["偏高 (60-80%)", "中性 (40-60%)"]:
    for direction in ["↑上升", "↓下降"]:
        sub = df[(df["zone"] == z) & (df["pct_dir"] == direction)]
        n = len(sub)
        if n < 5:
            continue
        print(f"\n  {z} × {direction}　（樣本數：{n} 週）")
        hdr = f"  {'統計量':<9}"
        for label in HORIZONS.values():
            hdr += f"  {label:>9}"
        print(hdr)
        print(f"  {'-'*65}")
        desc = sub[list(HORIZONS.values())].describe()
        for s in ["mean", "50%", "std"]:
            row = f"  {STAT_LABELS[s]:<9}"
            for label in HORIZONS.values():
                row += f"  {desc.loc[s, label]:>+8.1f}%"
            print(row)
        row_sr = f"  {'夏普比':<9}"
        for label in HORIZONS.values():
            std = sub[label].std()
            sr = sub[label].mean() / std if std > 0 else 0
            row_sr += f"  {sr:>+8.2f} "
        print(row_sr)

# ── 5. 視覺化 ─────────────────────────────────────────
fig = make_subplots(
    rows=4, cols=2,
    shared_xaxes=False,
    vertical_spacing=0.07,
    horizontal_spacing=0.06,
    subplot_titles=(
        "加權指數",
        "上市融資交易金額 + 2年百分位 + 月增速",
        "中位數報酬（各區間 × 持有期）",
        "夏普比率（各區間 × 持有期）",
        "中位數報酬：百分位↑上升中",
        "中位數報酬：百分位↓下降中",
    ),
    row_heights=[0.28, 0.20, 0.26, 0.26],
    specs=[
        [{"colspan": 2}, None],
        [{"colspan": 2, "secondary_y": True}, None],
        [{}, {}],
        [{}, {}],
    ]
)

COLORS = {
    "過熱 (≥80%)":  "#FF4B4B",
    "偏高 (60-80%)": "#FFA040",
    "中性 (40-60%)": "#AAAAAA",
    "偏低 (20-40%)": "#40AAFF",
    "低迷 (<20%)":  "#40FF80",
}

# ── Row 1：加權指數 ──────────────────────────────────
fig.add_trace(go.Scatter(
    x=taiex_w.index, y=taiex_w.values,
    mode="lines", name="加權指數",
    line=dict(color="#FF4B4B", width=1.5),
    hovertemplate="<b>%{x|%Y-%m-%d}</b><br>%{y:,.0f} 點<extra></extra>"
), row=1, col=1)

hot_mask = margin_pct >= 0.80
in_hot = False; hot_start = None
for date, is_hot in hot_mask.items():
    if is_hot and not in_hot:
        hot_start = date; in_hot = True
    elif not is_hot and in_hot:
        fig.add_vrect(x0=hot_start, x1=date,
            fillcolor="rgba(255,75,75,0.15)", line_width=0, row=1, col=1)
        in_hot = False
if in_hot:
    fig.add_vrect(x0=hot_start, x1=margin_pct.index[-1],
        fillcolor="rgba(255,75,75,0.15)", line_width=0, row=1, col=1)

# ── Row 2：上市融資交易金額 bar + 百分位線 ──────────────
for z in zone_order:
    sub = df_zones[df_zones["zone"] == z]
    fig.add_trace(go.Bar(
        x=sub.index, y=sub["margin"],
        name=z, marker_color=COLORS[z], opacity=0.85,
        showlegend=True,
        hovertemplate=f"<b>%{{x|%Y-%m-%d}}</b><br>上市融資交易金額：%{{y:,.0f}} 億元<br>區間：{z}<extra></extra>"
    ), row=2, col=1)

fig.add_trace(go.Scatter(
    x=margin_pct.index, y=margin_pct.values * 100,
    mode="lines", name="2年百分位(%)",
    line=dict(color="#FFD700", width=1.8, dash="dot"),
    hovertemplate="2年百分位：%{y:.0f}%<extra></extra>"
), row=2, col=1, secondary_y=True)

mom4_pos = mom4.where(mom4 >= 0, 0)
mom4_neg = mom4.where(mom4 <  0, 0)
fig.add_trace(go.Scatter(
    x=mom4_pos.index, y=mom4_pos.values,
    fill="tozeroy", fillcolor="rgba(64,200,96,0.22)",
    line=dict(color="rgba(64,200,96,0.55)", width=0.8),
    name="月增速(+)", showlegend=False,
    hovertemplate="月增速：%{y:+.1f}%<extra></extra>",
), row=2, col=1, secondary_y=True)
fig.add_trace(go.Scatter(
    x=mom4_neg.index, y=mom4_neg.values,
    fill="tozeroy", fillcolor="rgba(255,75,75,0.22)",
    line=dict(color="rgba(255,75,75,0.55)", width=0.8),
    name="月增速(-)", showlegend=False,
    hovertemplate="月增速：%{y:+.1f}%<extra></extra>",
), row=2, col=1, secondary_y=True)
fig.add_trace(go.Scatter(
    x=[margin_pct.index[0], margin_pct.index[-1]], y=[0, 0],
    mode="lines", line=dict(color="rgba(200,200,200,0.22)", width=1, dash="dot"),
    showlegend=False, hoverinfo="skip",
), row=2, col=1, secondary_y=True)

# ── Row 3 & 4：熱力圖資料準備 ────────────────────────
ZONE_SHORT = {
    "過熱 (≥80%)":  "過熱 ≥80%",
    "偏高 (60-80%)": "偏高 60~80%",
    "中性 (40-60%)": "中性 40~60%",
    "偏低 (20-40%)": "偏低 20~40%",
    "低迷 (<20%)":  "低迷 <20%",
}
zone_display = [ZONE_SHORT[z] for z in reversed(zone_order)]
horiz_labels = list(HORIZONS.values())

z_median, z_sharpe = [], []
text_median, text_sharpe = [], []
cdata_median, cdata_sharpe = [], []

z_up, z_dn = [], []
text_up, text_dn = [], []
cdata_up, cdata_dn = [], []

for zshort, zfull in zip(zone_display, reversed(zone_order)):
    sub     = df[df["zone"] == zfull]
    sub_up  = df[(df["zone"] == zfull) & (df["pct_dir"] == "↑上升")]
    sub_dn  = df[(df["zone"] == zfull) & (df["pct_dir"] == "↓下降")]
    n       = len(sub)
    n_u, n_d = len(sub_up), len(sub_dn)

    rm, rs, tm, ts, cm, csd = [], [], [], [], [], []
    ru, rd, tu, td, cu, cd  = [], [], [], [], [], []

    for label in horiz_labels:
        med = sub[label].median()
        mn  = sub[label].mean()
        std = sub[label].std()
        sr  = mn / std if std > 0 else 0

        med_u = sub_up[label].median() if n_u >= 3 else np.nan
        med_d = sub_dn[label].median() if n_d >= 3 else np.nan

        rm.append(med);   rs.append(sr)
        tm.append(f"{med:+.1f}%"); ts.append(f"{sr:+.2f}")
        cm.append(f"<b>{zfull}</b><br>{label}<br>中位數 {med:+.1f}%  均值 {mn:+.1f}%<br>夏普比 {sr:+.2f}  樣本 {n} 週")
        csd.append(f"<b>{zfull}</b><br>{label}<br>夏普比 {sr:+.2f}<br>中位數 {med:+.1f}%  均值 {mn:+.1f}%  樣本 {n} 週")

        ru.append(med_u); rd.append(med_d)
        tu.append(f"{med_u:+.1f}%" if not np.isnan(med_u) else "-")
        td.append(f"{med_d:+.1f}%" if not np.isnan(med_d) else "-")
        cu.append(f"<b>{zfull} ↑</b><br>{label}<br>中位數 {med_u:+.1f}%  樣本 {n_u} 週" if not np.isnan(med_u) else "樣本不足")
        cd.append(f"<b>{zfull} ↓</b><br>{label}<br>中位數 {med_d:+.1f}%  樣本 {n_d} 週" if not np.isnan(med_d) else "樣本不足")

    z_median.append(rm);   z_sharpe.append(rs)
    text_median.append(tm); text_sharpe.append(ts)
    cdata_median.append(cm); cdata_sharpe.append(csd)

    z_up.append(ru); z_dn.append(rd)
    text_up.append(tu); text_dn.append(td)
    cdata_up.append(cu); cdata_dn.append(cd)

# 色階
ret_cs = [
    [0.00, "#1A4F8A"], [0.35, "#1E2A50"],
    [0.50, "#1A1A2E"],
    [0.65, "#1A4A28"], [1.00, "#22BB55"],
]
sharpe_cs = [
    [0.00, "#8B1A1A"], [0.40, "#2A1A1E"],
    [0.50, "#1A1A2E"],
    [0.60, "#1A2A1A"], [1.00, "#22BB55"],
]

# ── Row 3：整體中位數 + 夏普比 ────────────────────────
fig.add_trace(go.Heatmap(
    z=z_median, x=horiz_labels, y=zone_display,
    text=text_median, customdata=cdata_median,
    texttemplate="%{text}", textfont=dict(size=11, color="white"),
    hovertemplate="%{customdata}<extra></extra>",
    colorscale=ret_cs, zmid=0, zmin=-8, zmax=12,
    showscale=True,
    colorbar=dict(x=0.46, thickness=10, len=0.22, yanchor="bottom", y=0.27,
                  tickfont=dict(size=9, color="#AAAAAA"), ticksuffix="%",
                  title=dict(text="報酬", font=dict(size=9, color="#AAAAAA"), side="top")),
), row=3, col=1)

fig.add_trace(go.Heatmap(
    z=z_sharpe, x=horiz_labels, y=zone_display,
    text=text_sharpe, customdata=cdata_sharpe,
    texttemplate="%{text}", textfont=dict(size=11, color="white"),
    hovertemplate="%{customdata}<extra></extra>",
    colorscale=sharpe_cs, zmid=0, zmin=-1.0, zmax=1.0,
    showscale=True,
    colorbar=dict(x=1.01, thickness=10, len=0.22, yanchor="bottom", y=0.27,
                  tickfont=dict(size=9, color="#AAAAAA"),
                  title=dict(text="夏普比", font=dict(size=9, color="#AAAAAA"), side="top")),
), row=3, col=2)

# ── Row 4：方向分析（↑上升 vs ↓下降）─────────────────
fig.add_trace(go.Heatmap(
    z=z_up, x=horiz_labels, y=zone_display,
    text=text_up, customdata=cdata_up,
    texttemplate="%{text}", textfont=dict(size=11, color="white"),
    hovertemplate="%{customdata}<extra></extra>",
    colorscale=ret_cs, zmid=0, zmin=-8, zmax=12,
    showscale=False,
), row=4, col=1)

fig.add_trace(go.Heatmap(
    z=z_dn, x=horiz_labels, y=zone_display,
    text=text_dn, customdata=cdata_dn,
    texttemplate="%{text}", textfont=dict(size=11, color="white"),
    hovertemplate="%{customdata}<extra></extra>",
    colorscale=ret_cs, zmid=0, zmin=-8, zmax=12,
    showscale=False,
), row=4, col=2)

# ── 6. 版面設定 ──────────────────────────────────────
fig.update_layout(
    title=dict(text="上市融資交易金額過熱分析（2年滾動百分位，2009~2026，週資料）",
               font=dict(size=18, color="#F0F0F0"), x=0.5),
    height=1200,
    plot_bgcolor="#12121E", paper_bgcolor="#0C0C18",
    font=dict(color="#CCCCCC", family="Arial, sans-serif"),
    hovermode="x unified",
    barmode="stack",
    legend=dict(orientation="h", yanchor="bottom", y=1.01,
                xanchor="right", x=1, bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
    margin=dict(t=80, b=60, l=110, r=50),
    bargap=0.05,
)

fig.update_xaxes(gridcolor="#1F1F30", zeroline=False, tickfont=dict(color="#AAAAAA"))
fig.update_yaxes(gridcolor="#1F1F30", zeroline=False, tickfont=dict(color="#AAAAAA"))

fig.update_layout(
    xaxis=dict(
        type='date',
        rangeslider=dict(visible=True, bgcolor="#1A1A2E", thickness=0.04),
        rangeselector=dict(
            buttons=[
                dict(count=3,  label="3年",  step="year", stepmode="backward"),
                dict(count=5,  label="5年",  step="year", stepmode="backward"),
                dict(count=10, label="10年", step="year", stepmode="backward"),
                dict(step="all", label="全部"),
            ],
            bgcolor="#1E1E2E", activecolor="#FF4B4B",
            bordercolor="#444", borderwidth=1,
            font=dict(color="#CCCCCC", size=11),
            x=0, xanchor="left",
        ),
        range=[margin_w.index[-1] - pd.DateOffset(years=5), margin_w.index[-1] + pd.DateOffset(months=1)],
    ),
    xaxis2=dict(type='date', matches='x', showticklabels=True),
)

# Y 軸
fig.update_yaxes(tickformat=",d", title_text="點",
    title_font=dict(size=11, color="#999"),
    fixedrange=False, autorange=True,
    row=1, col=1)
fig.update_yaxes(tickformat=",d", ticksuffix=" 億", title_text="上市融資交易金額（億元）",
    title_font=dict(size=11, color="#999"), row=2, col=1, secondary_y=False)
fig.update_yaxes(range=[-35, 100], ticksuffix="%", title_text="百分位／月增速",
    title_font=dict(size=11, color="#FFD700"),
    tickfont=dict(color="#FFD700"),
    tickvals=[-20, 0, 20, 40, 60, 80, 100],
    gridcolor="rgba(0,0,0,0)", row=2, col=1, secondary_y=True)

# 熱力圖 y 軸
for r in [3, 4]:
    fig.update_yaxes(tickfont=dict(color="#CCCCCC", size=11),
                     gridcolor="rgba(0,0,0,0)", row=r, col=1)
    fig.update_yaxes(showticklabels=False,
                     gridcolor="rgba(0,0,0,0)", row=r, col=2)
    fig.update_xaxes(tickfont=dict(color="#AAAAAA", size=11),
                     gridcolor="rgba(0,0,0,0)", row=r, col=1)
    fig.update_xaxes(tickfont=dict(color="#AAAAAA", size=11),
                     gridcolor="rgba(0,0,0,0)", row=r, col=2)

# 手動 y domain（4 行）
fig.update_layout(
    yaxis =dict(domain=[0.80, 1.00]),   # 圖一
    yaxis2=dict(domain=[0.54, 0.68]),   # 圖二 primary
    yaxis3=dict(domain=[0.54, 0.68]),   # 圖二 secondary
    yaxis4=dict(domain=[0.28, 0.47]),   # 圖三左
    yaxis5=dict(domain=[0.28, 0.47]),   # 圖三右
    yaxis6=dict(domain=[0.00, 0.22]),   # 圖四左
    yaxis7=dict(domain=[0.00, 0.22]),   # 圖四右
)

for ann in fig.layout.annotations:
    ann.font.color = "#BBBBBB"
    ann.font.size = 12

fig.write_html("margin_heat_analysis.html", include_plotlyjs=True)
print("圖表已儲存 → margin_heat_analysis.html")
