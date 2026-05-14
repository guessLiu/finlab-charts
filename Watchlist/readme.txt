Watchlist 使用說明
==================

啟動
----
雙擊「開啟Watchlist.bat」。
命令視窗關掉後服務停止，使用時保持開著。

若出現「Python not found」：手動安裝 Python 3.12 → https://www.python.org/downloads/


交易流程
--------
Hot      主畫面時間軸，保留最近 10 個選股日期，統計入選次數與熱度。
Waiting  觀察等待區，適合基本面不錯但尚未到進場點的股票，重點是 note。
Holding  持股區，獨立顯示，不污染盤感。記錄買進日、成本、note、來源日期。

新增第 11 個日期時，系統會提示是否將最舊日期的股票封存到 Waiting。


主要功能
--------
- 新增 / 刪除選股（單格、整欄、整股）
- Hot → Waiting → Holding 流程按鈕
- 搜尋股號或名稱
- 排序：入選次數 / 首次入選日 / 選入後報酬 / MAE / MFE/MAE / 5日漲幅
- 滑過股票查看 5D、1M、3M 報酬及 MFE / MAE
- 5 日收盤走勢小圖
- 匯出 CSV / 備份 JSON / 匯入


資料檔
------
stock_watchlist_auto.json   選股資料（自動存檔）
notes_auto.json             備註資料（自動存檔）
watchlist_config.json       設定（備份資料夾路徑）
backups/                    啟動時自動備份，保留 7 天內所有快照


匯入格式
--------
支援以下 CSV / JSON：

1. 本工具匯出的 CSV 或 JSON
2. 只有股號的 CSV（逐列，匯入到今天）
3. 欄位式 CSV：日期,股票代號
4. 欄式 CSV（第一列日期，下方各欄股號）

換電腦：帶整個 Watchlist 資料夾即可。


近期報酬
--------
資料來源：Yahoo Finance（自動更新）

5D      近 5 交易日
1M      近 21 交易日
3M      近 63 交易日
MFE     近 1 個月最大有利報酬
MAE     近 1 個月最大不利報酬
選入後  第一次選入日至今累積報酬

網路失敗時保留舊值，不清空。
