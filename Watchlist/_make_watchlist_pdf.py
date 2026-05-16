"""
產生「選股紀錄系統 使用手冊 PDF」
Playwright 將 HTML 模板直接印成 A4 PDF
"""
import pathlib
from playwright.sync_api import sync_playwright

BASE = pathlib.Path(__file__).parent
OUT  = BASE / "選股紀錄系統_使用手冊.pdf"


HTML = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<style>
@page { margin: 15mm 16mm; }
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Microsoft JhengHei', 'Noto Sans TC', 'Arial', sans-serif;
  font-size: 13px; line-height: 1.75; color: #1a1a1a;
}
h1 { font-size: 28px; font-weight: 800; color: #111; margin-bottom: 4px; }
h2 {
  font-size: 16px; font-weight: 700; color: #fff;
  background: #1a3a5c; padding: 7px 14px; border-radius: 6px;
  margin: 26px 0 12px;
}
h3 {
  font-size: 13.5px; font-weight: 700; color: #1a3a5c;
  border-left: 4px solid #2e78c7; padding-left: 9px;
  margin: 16px 0 8px;
}
p  { margin: 5px 0 9px; color: #333; }
ul { padding-left: 20px; margin: 5px 0 10px; }
li { margin-bottom: 3px; }

.subtitle { color: #555; font-size: 14px; margin-bottom: 6px; }
.date     { color: #888; font-size: 12px; margin-bottom: 24px; }

.page-break { page-break-before: always; padding-top: 0; }

.tip {
  background: #fff8e6; border-left: 4px solid #e6a817;
  padding: 8px 13px; border-radius: 4px; margin: 9px 0 12px;
  font-size: 12.5px; color: #555;
}
.tip strong { color: #b07010; }

.note {
  background: #eef5ff; border-left: 4px solid #2e78c7;
  padding: 8px 13px; border-radius: 4px; margin: 9px 0 12px;
  font-size: 12.5px; color: #2a4a7a;
}

table {
  border-collapse: collapse; width: 100%; margin: 8px 0 14px;
  font-size: 12px;
}
th {
  background: #e8eef6; border: 1px solid #bbb;
  padding: 5px 10px; font-weight: 700; text-align: left; color: #1a3a5c;
}
td { border: 1px solid #ccc; padding: 5px 10px; }
tr:nth-child(even) td { background: #f8f9fb; }

.badge {
  display: inline-block; padding: 2px 8px; border-radius: 4px;
  font-size: 11px; font-weight: 700; margin-right: 4px;
}
.badge-hot     { background: #ffedcc; color: #b05000; border: 1px solid #e6a040; }
.badge-waiting { background: #fff3cd; color: #7a5c00; border: 1px solid #c8a830; }
.badge-holding { background: #d4f0db; color: #1a6630; border: 1px solid #4caf70; }
.badge-new     { background: #d6e9ff; color: #0050a0; border: 1px solid #5090d0; }
.badge-fu      {
  display: inline-block; width: 22px; height: 22px; line-height: 22px;
  text-align: center; background: #dbeffe; color: #0070b8;
  border: 1px solid #5aabdc; border-radius: 4px;
  font-size: 12px; font-weight: 700; margin-right: 4px; vertical-align: middle;
}

.flow-row {
  display: flex; align-items: center; gap: 8px; margin: 12px 0 6px;
}
.flow-step {
  background: #1a3a5c; color: #fff;
  padding: 5px 12px; border-radius: 20px; font-size: 13px; font-weight: 700;
  white-space: nowrap;
}
.flow-arrow { color: #888; font-size: 18px; }

.modal-box {
  background: #f5f7fa; border: 1px solid #bbb; border-radius: 8px;
  padding: 12px 16px; margin: 8px 0 12px; font-size: 12.5px; color: #333;
  font-family: monospace;
}
.modal-box .mline { margin-bottom: 3px; }
.modal-box .mlabel { color: #666; min-width: 88px; display: inline-block; }
.modal-box .mval   { color: #1a3a5c; font-weight: 700; }
.modal-box .mbtns  { margin-top: 8px; }
.btn-sim {
  display: inline-block; padding: 3px 10px;
  border: 1px solid; border-radius: 4px; font-size: 11px;
  font-weight: 700; margin-right: 5px; font-family: sans-serif;
}
.btn-green  { background: #d4f0db; border-color: #4caf70; color: #1a6630; }
.btn-blue   { background: #dbeffe; border-color: #5aabdc; color: #0050a0; }
.btn-gray   { background: #f0f0f0; border-color: #aaa;    color: #444; }
.btn-red    { background: #fde8e8; border-color: #e06060; color: #9a1a1a; }

.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin: 8px 0; }
.term { margin-bottom: 10px; }
.term-title { font-weight: 700; color: #1a3a5c; font-size: 13px; }
.term-body  { color: #444; font-size: 12.5px; margin-top: 2px; }

.cover-divider { border: none; border-top: 2px solid #2e78c7; margin: 18px 0; }
</style>
</head>
<body>

<!-- ══════════ 封面 ══════════ -->
<h1>選股紀錄系統</h1>
<p class="subtitle">使用手冊 — 從熱門股到持股管理的完整操作指南</p>
<p class="date">2026-05-16 版本</p>
<hr class="cover-divider">

<h2>系統目的</h2>
<p>
  選股紀錄系統將每天的熱門股資料與個人的選股判斷整合在一個頁面。
  核心流程是：Hot（熱門觀察）→ Waiting（等待進場）→ Holding（已建倉持股），
  讓選股、等待、持倉三個階段都有清楚的紀錄與管理。
</p>

<div class="flow-row">
  <div class="flow-step">🔥 Hot</div>
  <div class="flow-arrow">→</div>
  <div class="flow-step">📌 Waiting</div>
  <div class="flow-arrow">→</div>
  <div class="flow-step">💼 Holding</div>
</div>

<h2>啟動方式</h2>
<p>
  雙擊 <strong>Watchlist.bat</strong>，等命令視窗出現「Server running」後，
  瀏覽器會自動開啟。使用期間保持命令視窗開著；關掉後服務停止。
</p>
<div class="tip">
  若出現「Python not found」，請手動安裝 Python 3.12：
  <strong>https://www.python.org/downloads/</strong>
</div>


<!-- ══════════ Hot 主畫面 ══════════ -->
<div class="page-break">
<h2>Hot 主畫面</h2>
<p>
  主畫面以<strong>時間軸表格</strong>顯示最近 10 個選股日期的紀錄。
  每欄代表一個日期，每列代表一檔股票，顯示各日期是否有被選入。
</p>

<h3>頂欄功能列</h3>
<table>
  <tr><th>元件</th><th>功能</th></tr>
  <tr><td>＋ 新增選股</td><td>輸入日期與股號（支援逗號、換行混合）</td></tr>
  <tr><td>排序選單</td><td>依入選次數、首次入選日、選入後報酬、MAE、MFE/MAE、5日漲幅排序</td></tr>
  <tr><td>搜尋欄</td><td>即時搜尋股號或名稱</td></tr>
  <tr><td>匯出 CSV / 備份 JSON / 匯入</td><td>資料匯出與還原</td></tr>
</table>

<h3>每列股票的操作（滑鼠移上後顯示）</h3>
<table>
  <tr><th>按鈕</th><th>說明</th></tr>
  <tr>
    <td><span class="badge-fu">基</span></td>
    <td>開啟基本面頁面：台股開 <strong>Goodinfo</strong>，美股開 <strong>Yahoo Finance</strong></td>
  </tr>
  <tr>
    <td>📌（橘色）</td>
    <td>加入 Waiting 觀察區，同時記錄觀察 note</td>
  </tr>
  <tr>
    <td>●（綠色）</td>
    <td>加入 Holding 持股區，開啟買進表單</td>
  </tr>
  <tr>
    <td>✎</td>
    <td>編輯該股的備註文字</td>
  </tr>
  <tr>
    <td>✕（紅色）</td>
    <td>刪除此股所有紀錄（含所有日期）</td>
  </tr>
</table>

<h3>近期報酬欄（滑鼠懸停彈出）</h3>
<table>
  <tr><th>欄位</th><th>計算方式</th></tr>
  <tr><td>5D</td><td>近 5 個交易日報酬</td></tr>
  <tr><td>1M</td><td>近 21 個交易日報酬</td></tr>
  <tr><td>3M</td><td>近 63 個交易日報酬</td></tr>
  <tr><td>MFE</td><td>近 1 個月最大有利報酬（Max Favorable Excursion）</td></tr>
  <tr><td>MAE</td><td>近 1 個月最大不利報酬（Max Adverse Excursion）</td></tr>
  <tr><td>選入後</td><td>第一次入選日至今累積報酬</td></tr>
</table>
<div class="note">資料來源：Yahoo Finance，每次啟動自動更新，離線時保留舊值。</div>

<h3>熱度色彩</h3>
<p>
  股票的入選次數越多，Badge 顏色越鮮豔（1 次為灰色，多次為彩色漸層），
  方便快速辨識高頻選入的強勢股。
</p>

<h3>日期管理</h3>
<p>
  系統保留最近 10 個選股日期。新增第 11 個日期時，
  系統提示是否將最舊日期的股票<strong>封存到 Waiting</strong>。
  點擊日期欄標題可刪除整欄（該日期所有紀錄）。
</p>
</div>


<!-- ══════════ Waiting ══════════ -->
<div class="page-break">
<h2>Waiting 觀察等待區</h2>
<p>
  Waiting 是「基本面不錯但尚未到進場點」的暫存區。
  重點是寫清楚 <strong>note（觀察原因）</strong>，方便回來複查時快速理解當初的判斷。
</p>

<h3>加入 Waiting</h3>
<ul>
  <li>在 Hot 表格中，滑鼠移到股票列 → 點擊 📌 按鈕</li>
  <li>輸入觀察 note（可空白）→ 確認</li>
  <li>或在 Hot 表格點擊「編輯 Waiting」更新 note</li>
</ul>

<h3>Waiting 卡片操作</h3>
<table>
  <tr><th>按鈕</th><th>說明</th></tr>
  <tr><td><span class="badge-fu">基</span></td><td>開啟基本面頁面（台股 Goodinfo / 美股 Yahoo Finance）</td></tr>
  <tr><td>編輯</td><td>修改觀察 note</td></tr>
  <tr><td><span style="color:#2a7a3a;font-weight:700">轉持股</span></td><td>開啟買進表單，轉入 Holding</td></tr>
  <tr><td><span style="color:#c03030;font-weight:700">移除</span></td><td>從 Waiting 刪除（Hot 紀錄不受影響）</td></tr>
</table>

<div class="note">
  Waiting 卡片也顯示「60MA 乖離率」與來源日期，方便判斷現在是否接近進場條件。
</div>


<!-- ══════════ Holding ══════════ -->
<h2>Holding 持股區</h2>
<p>
  Holding 記錄已建倉的持股，支援<strong>分批買進</strong>，
  自動計算加權平均成本與未實現報酬。
</p>

<h3>加入 Holding（首次買進）</h3>
<p>
  從 Waiting 按「轉持股」，或在 Hot 表格點擊 ● 按鈕，開啟買進表單：
</p>
<div class="modal-box">
  <div class="mline"><span class="mlabel">買進日期</span><span class="mval">2026-05-16</span></div>
  <div class="mline"><span class="mlabel">價格</span><span class="mval">102.50</span></div>
  <div class="mline"><span class="mlabel">數量</span><span class="mval">2（可小數）</span></div>
  <div class="mline"><span class="mlabel">Note</span><span class="mval">突破前高買進</span></div>
  <div class="mbtns">
    <span class="btn-sim btn-gray">取消</span>
    <span class="btn-sim btn-green">確認買進</span>
  </div>
</div>

<h3>Holding 卡片顯示</h3>
<p>持股卡片摘要顯示平均成本、總數量、批次數、已持有天數：</p>
<div class="modal-box">
  <div class="mline"><span class="mlabel">股票</span><span class="mval">2330 台積電 &nbsp;&nbsp; +5.3%</span></div>
  <div class="mline"><span class="mlabel">成本</span><span class="mval">106.67 ｜ 數量：3 ｜ 批次：2</span></div>
  <div class="mline"><span class="mlabel">買進</span><span class="mval">2026-05-10 ｜ 持有：6 日</span></div>
  <div class="mbtns">
    <span class="btn-sim btn-blue">基</span>
    <span class="btn-sim btn-green">加碼</span>
    <span class="btn-sim btn-gray">編輯</span>
    <span class="btn-sim btn-gray">轉回等待</span>
    <span class="btn-sim btn-red">移除</span>
  </div>
</div>
</div>


<!-- ══════════ 加碼 / 編輯 ══════════ -->
<div class="page-break">
<h2>分批買進操作 <span class="badge badge-new">新功能</span></h2>

<h3>加碼（快速新增一筆）</h3>
<p>
  在 Holding 卡片按「加碼」，輸入本次買進日期、價格、數量，
  系統即時顯示加碼後的新均價：
</p>
<div class="modal-box">
  <div class="mline"><span class="mlabel">買進日期</span><span class="mval">2026-05-14</span></div>
  <div class="mline"><span class="mlabel">價格</span><span class="mval">110.00</span></div>
  <div class="mline"><span class="mlabel">數量</span><span class="mval">2</span></div>
  <div class="mline" style="margin-top:6px;color:#888">目前均價：<strong>100</strong>　數量：<strong>1</strong></div>
  <div class="mline" style="color:#1a6630">加碼後均價：<strong>106.67</strong>　新數量：<strong>3</strong></div>
  <div class="mbtns">
    <span class="btn-sim btn-gray">取消</span>
    <span class="btn-sim btn-green">確認加碼</span>
  </div>
</div>
<div class="tip">
  <strong>平均成本公式：</strong>
  新均價 = (舊均價 × 舊數量 + 新價格 × 新數量) ÷ (舊數量 + 新數量)
</div>

<h3>編輯持股（完整批次管理）</h3>
<p>
  按「編輯」開啟完整 modal，可逐筆修改或刪除批次紀錄：
</p>
<div class="modal-box">
  <div class="mline" style="color:#1a6630">均價：<strong>106.67</strong>　總數量：<strong>3</strong>　批次：<strong>2</strong></div>
  <table style="margin:8px 0 6px;font-size:12px">
    <tr>
      <th style="background:#e8eef6">日期</th>
      <th style="background:#e8eef6">價格</th>
      <th style="background:#e8eef6">數量</th>
      <th style="background:#e8eef6"></th>
    </tr>
    <tr><td>2026-05-10</td><td>100.00</td><td>1</td><td style="color:#c03030;text-align:center">✕</td></tr>
    <tr><td>2026-05-14</td><td>110.00</td><td>2</td><td style="color:#c03030;text-align:center">✕</td></tr>
  </table>
  <div class="mline"><span class="btn-sim btn-gray">＋ 新增一筆</span></div>
  <div class="mline" style="margin-top:6px"><span class="mlabel">Note</span><span class="mval">突破買，加碼</span></div>
  <div class="mbtns">
    <span class="btn-sim btn-gray">取消</span>
    <span class="btn-sim btn-green">儲存</span>
  </div>
</div>

<table>
  <tr><th>規則</th><th>說明</th></tr>
  <tr><td>自動重算</td><td>儲存時由所有 lots 重新計算平均成本與總數量</td></tr>
  <tr><td>最少一筆</td><td>不允許刪除全部批次</td></tr>
  <tr><td>數量允許小數</td><td>方便用「張」「股」或比例單位</td></tr>
  <tr><td>向下相容</td><td>舊持股資料（只有成本無批次）自動視為單筆 lot</td></tr>
</table>

<h3>轉回等待</h3>
<p>
  按「轉回等待」將持股移回 Waiting，系統會要求更新 note。
  原有的 Hot 紀錄不受影響。
</p>
</div>


<!-- ══════════ 基本面連結 ══════════ -->
<div class="page-break">
<h2>基本面連結按鈕 <span class="badge badge-new">新功能</span></h2>
<p>
  每檔股票旁都有 <span class="badge-fu">基</span> 小方塊按鈕，
  一鍵開啟外部基本面資料頁面：
</p>
<table>
  <tr><th>交易所</th><th>開啟頁面</th></tr>
  <tr>
    <td>台股（TWSE / TPEx）</td>
    <td>Goodinfo — 損益表、月營收、財務比率</td>
  </tr>
  <tr>
    <td>美股</td>
    <td>Yahoo Finance Financials — 財報摘要</td>
  </tr>
</table>

<p>按鈕出現位置：</p>
<ul>
  <li><strong>Hot 表格</strong>：滑鼠移到股票列時，出現在操作按鈕群組中</li>
  <li><strong>Waiting 卡片</strong>：卡片 hover 後在動作欄顯示</li>
  <li><strong>Holding 卡片</strong>：常駐顯示在動作欄</li>
</ul>
<div class="note">
  Watchlist 不抓取基本面數字，只做外部連結，程式本身保持輕量。
</div>


<!-- ══════════ 資料管理 ══════════ -->
<h2>資料管理</h2>

<h3>自動備份</h3>
<p>
  每次啟動時自動備份目前資料到 <code>backups/</code> 資料夾，
  保留 7 天內所有快照，超過 7 天自動清理。
</p>

<h3>匯出</h3>
<table>
  <tr><th>格式</th><th>用途</th></tr>
  <tr><td>匯出 CSV</td><td>在 Excel / Google Sheets 查看所有日期紀錄</td></tr>
  <tr><td>備份 JSON</td><td>完整資料備份，包含 Hot / Waiting / Holding</td></tr>
</table>

<h3>匯入支援格式</h3>
<table>
  <tr><th>格式</th><th>說明</th></tr>
  <tr><td>本工具匯出的 CSV / JSON</td><td>完整還原</td></tr>
  <tr><td>只有股號的 CSV（逐列）</td><td>匯入到今天日期</td></tr>
  <tr><td>欄位式 CSV：日期, 股票代號</td><td>指定日期匯入</td></tr>
  <tr><td>欄式 CSV（第一列為日期）</td><td>多欄多日期一次匯入</td></tr>
</table>

<h3>換電腦 / 分享</h3>
<p>
  帶走整個 <strong>Watchlist 資料夾</strong>即可。
  資料檔說明：
</p>
<table>
  <tr><th>檔案</th><th>內容</th></tr>
  <tr><td>stock_watchlist_auto.json</td><td>選股主資料（含 Hot / Waiting / Holding）</td></tr>
  <tr><td>notes_auto.json</td><td>股票備註</td></tr>
  <tr><td>watchlist_config.json</td><td>備份路徑設定</td></tr>
  <tr><td>backups/</td><td>自動備份快照</td></tr>
</table>
</div>


<!-- ══════════ 名詞解釋 ══════════ -->
<div class="page-break">
<h2>名詞解釋</h2>
<div class="two-col">
  <div class="term">
    <div class="term-title">Hot</div>
    <div class="term-body">主畫面選股紀錄，以時間軸表格呈現，方便觀察哪些股票持續出現。</div>
  </div>
  <div class="term">
    <div class="term-title">Waiting</div>
    <div class="term-body">觀察等待區，用於記錄「值得注意但尚未進場」的股票，需搭配 note 說明觀察原因。</div>
  </div>
  <div class="term">
    <div class="term-title">Holding</div>
    <div class="term-body">持股區，記錄已建倉股票的買進成本、數量、批次與報酬。</div>
  </div>
  <div class="term">
    <div class="term-title">平均成本（cost）</div>
    <div class="term-body">所有批次的加權平均買進價格，系統自動計算。報酬 = (現價 - cost) / cost。</div>
  </div>
  <div class="term">
    <div class="term-title">lots（買進批次）</div>
    <div class="term-body">每次加碼買進的個別紀錄（日期、價格、數量），內部儲存但平常不顯示。</div>
  </div>
  <div class="term">
    <div class="term-title">選入後報酬</div>
    <div class="term-body">從第一次入選 Hot List 至今的累積報酬，反映選股的長期表現。</div>
  </div>
  <div class="term">
    <div class="term-title">MFE / MAE</div>
    <div class="term-body">
      MFE（最大有利報酬）：近 1 個月最高漲幅。<br>
      MAE（最大不利報酬）：近 1 個月最大跌幅。
    </div>
  </div>
  <div class="term">
    <div class="term-title">60MA 乖離率</div>
    <div class="term-body">現價與 60 日均線的偏差百分比，顯示在 Waiting 卡片，輔助判斷進場時機。</div>
  </div>
  <div class="term">
    <div class="term-title">Goodinfo</div>
    <div class="term-body">台灣免費財務資訊網站，可查月營收、毛利率、EPS 等基本面數字。</div>
  </div>
  <div class="term">
    <div class="term-title">Yahoo Finance Financials</div>
    <div class="term-body">美股財報摘要頁面，含損益表、資產負債表等基本財務數據。</div>
  </div>
</div>

<div class="tip" style="margin-top:20px">
  <strong>小提醒：</strong>
  Watchlist 不做完整帳本，不記錄賣出、不計算已實現損益。
  目的是輔助選股決策流程，而非取代券商的交易紀錄。
</div>
</div>

</body>
</html>"""


def main():
    tmp = BASE / "_watchlist_manual_tmp.html"
    tmp.write_text(HTML, encoding="utf-8")

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto(f"file:///{tmp}", wait_until="networkidle")
        page.wait_for_timeout(300)
        pdf_bytes = page.pdf(
            format="A4",
            margin={"top": "15mm", "bottom": "15mm",
                    "left": "16mm", "right": "16mm"},
            display_header_footer=False,
            print_background=True,
        )
        browser.close()

    OUT.write_bytes(pdf_bytes)
    tmp.unlink(missing_ok=True)
    print(f"完成：{OUT}")


if __name__ == "__main__":
    main()
