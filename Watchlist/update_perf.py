"""
從 Yahoo Finance 抓取近期價格，計算每支觀察股的：
  5D 漲幅  = (今日收盤 - 5交易日前收盤) / 5交易日前收盤
  1M 漲幅  = (今日收盤 - 21交易日前收盤) / 21交易日前收盤
  3M 漲幅  = (今日收盤 - 63交易日前收盤) / 63交易日前收盤
  1M MFE   = 近21交易日最高點相對21交易日前收盤的漲幅
  1M MAE   = 近21交易日最低點相對21交易日前收盤的跌幅
  選入後報酬 = (最新收盤 - 第一次選入日收盤) / 第一次選入日收盤

股票清單來源（依序嘗試）：
  1. 目錄內最新的 stock_watchlist_*.json（備份檔）
  2. HTML 內現有的 perfData 鍵值（已更新過一次後可免 JSON）
"""
import json, re, sys, time
from pathlib import Path
from datetime import datetime, timezone, timedelta
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

HERE      = Path(__file__).parent
HTML_PATH = HERE / 'stock_watchlist.html'
TW_TZ     = timezone(timedelta(hours=8))

def latest_watchlist_json():
    files = sorted(HERE.glob('stock_watchlist_*.json'), key=lambda p: p.stat().st_mtime)
    if not files:
        return None, {}
    path = files[-1]
    raw = json.loads(path.read_text('utf-8'))
    return path, raw

def hot_data(raw):
    if isinstance(raw, dict) and any(k in raw for k in ('hot', 'waiting', 'holding')):
        hot = raw.get('hot')
        return hot if isinstance(hot, dict) else {}
    return raw if isinstance(raw, dict) else {}

# ── 股票清單 ─────────────────────────────────────────────
def stocks_from_json():
    path, raw = latest_watchlist_json()
    raw = hot_data(raw)
    if not raw:
        return []
    codes = set()
    for stocks in raw.values():
        if isinstance(stocks, list):
            codes.update(str(s).strip() for s in stocks if s)
    if codes:
        print(f'股票清單來源：{path.name}（{len(codes)} 支）')
    return list(codes)

def first_entry_dates():
    _, raw = latest_watchlist_json()
    raw = hot_data(raw)
    first = {}
    for date in sorted(raw.keys()):
        stocks = raw.get(date)
        if not isinstance(stocks, list):
            continue
        for stock in stocks:
            code = str(stock).strip()
            if code and code not in first:
                first[code] = date
    return first

def stocks_from_html():
    html = HTML_PATH.read_text('utf-8')
    s = html.find('/* __PERF_DATA__ */')
    e = html.find('/* __PERF_DATA_END__ */', s)
    if s < 0 or e < 0:
        return []
    block = html[s:e]
    # greedy [\s\S]* 從最後一個 } 往回回溯，正確匹配整個 JSON object
    m = re.search(r'let perfData\s*=\s*(\{[\s\S]*\})\s*;', block)
    if not m:
        return []
    try:
        d = json.loads(m.group(1))
        if d:
            print(f'股票清單來源：HTML perfData（{len(d)} 支）')
            return list(d.keys())
    except Exception as ex:
        print(f'讀取 perfData 失敗：{ex}')
    return []

def perf_from_html():
    html = HTML_PATH.read_text('utf-8')
    s = html.find('/* __PERF_DATA__ */')
    e = html.find('/* __PERF_DATA_END__ */', s)
    if s < 0 or e < 0:
        return {}
    block = html[s:e]
    m = re.search(r'let perfData\s*=\s*(\{[\s\S]*\})\s*;', block)
    if not m:
        return {}
    try:
        d = json.loads(m.group(1))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}

def load_twse_codes():
    html = HTML_PATH.read_text('utf-8')
    m = re.search(r'let embeddedTWSECodes\s*=\s*(\[.*?\]);', html, re.DOTALL)
    return set(json.loads(m.group(1))) if m else set()

# ── Yahoo Finance ────────────────────────────────────────
def is_us_stock(code):
    return bool(re.match(r'^[A-Z]{1,5}$', code))

def get_json(url, timeout=30):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'application/json',
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))

def fetch_prices(code, is_twse):
    if is_us_stock(code):
        suffix = ''
    elif is_twse:
        suffix = '.TW'
    else:
        suffix = '.TWO'
    url = (f'https://query1.finance.yahoo.com/v8/finance/chart/'
           f'{code}{suffix}?range=5y&interval=1d')
    data   = get_json(url)
    result = data['chart']['result'][0]
    ts_list = result['timestamp']
    q       = result['indicators']['quote'][0]
    prices  = {}
    for i, ts in enumerate(ts_list):
        d = datetime.fromtimestamp(ts, tz=TW_TZ).strftime('%Y-%m-%d')
        prices[d] = {
            'close': q['close'][i],
            'high':  q['high'][i],
            'low':   q['low'][i],
        }
    return prices

# ── 計算指標（以更新日為基準，往回看） ──────────────────
def entry_price_for_date(prices, entry_date):
    days = sorted(prices.keys())
    if not days or not entry_date:
        return None, None
    prior = [d for d in days if d <= entry_date and prices[d]['close'] is not None]
    if prior:
        d = prior[-1]
        return d, prices[d]['close']
    later = [d for d in days if d >= entry_date and prices[d]['close'] is not None]
    if later:
        d = later[0]
        return d, prices[d]['close']
    return None, None

def calc(prices, entry_date=None):
    days = sorted(prices.keys())
    if len(days) < 6:
        return None

    today_close = prices[days[-1]]['close']
    if today_close is None:
        return None

    m = {'updated': days[-1]}
    spark = [prices[d]['close'] for d in days[-5:] if prices[d]['close'] is not None]
    if len(spark) >= 2:
        m['spark5'] = [round(v, 4) for v in spark]

    def add_return(key, lookback):
        if len(days) < lookback + 1:
            return None
        base = prices[days[-lookback - 1]]['close']
        if base:
            m[key] = round((today_close - base) / base * 100, 2)
        return base

    add_return('5d', 5)
    base_1m = add_return('1m', 21)
    add_return('3m', 63)

    entry_px_date, entry_price = entry_price_for_date(prices, entry_date)
    if entry_date and entry_price:
        m['since_date'] = entry_date
        m['since_price_date'] = entry_px_date
        m['entry_price'] = round(entry_price, 4)
        m['latest_price'] = round(today_close, 4)
        m['since_ret'] = round((today_close - entry_price) / entry_price * 100, 2)
        try:
            m['since_days'] = max(0, (datetime.fromisoformat(days[-1]) - datetime.fromisoformat(entry_date)).days)
        except ValueError:
            pass

    if base_1m:
        window = days[-21:]   # 最近21個交易日（約1個月，含今日）
        highs  = [prices[d]['high'] for d in window if prices[d]['high'] is not None]
        lows   = [prices[d]['low']  for d in window if prices[d]['low']  is not None]
        if highs:
            m['mfe_1m'] = round((max(highs) - base_1m) / base_1m * 100, 2)
        if lows:
            m['mae_1m'] = round((min(lows)  - base_1m) / base_1m * 100, 2)

    # 60MA 乖離率
    if len(days) >= 60:
        closes60 = [prices[d]['close'] for d in days[-60:] if prices[d]['close'] is not None]
        if len(closes60) == 60:
            ma60 = sum(closes60) / 60
            if ma60:
                m['ma60_bias'] = round((today_close - ma60) / ma60 * 100, 2)

    return m

# ── 嵌入 HTML ────────────────────────────────────────────
def embed(perf):
    html = HTML_PATH.read_text('utf-8')
    if '/* __PERF_DATA__ */' not in html:
        print('[ERROR] 找不到 HTML 標記區塊')
        return False
    blob = json.dumps(perf, ensure_ascii=False, separators=(',', ':'))
    new_block = (
        '/* __PERF_DATA__ */\n'
        f'let perfData = {blob};\n'
        '/* __PERF_DATA_END__ */'
    )
    updated = re.sub(
        r'/\* __PERF_DATA__ \*/[\s\S]*?/\* __PERF_DATA_END__ \*/',
        new_block, html
    )
    if updated == html:
        print('資料無變化，略過寫入')
        return True
    HTML_PATH.write_text(updated, 'utf-8')
    return True

# ── 主流程 ───────────────────────────────────────────────
def main():
    print('=== 更新選股績效 ===\n')

    stocks = stocks_from_json() or stocks_from_html()
    if not stocks:
        print('[SKIP] 找不到股票清單。')
        print('       請先在 HTML 點「備份 JSON」存到此資料夾，再重新執行。')
        return

    twse = load_twse_codes()
    entry_dates = first_entry_dates()
    existing_perf = perf_from_html()
    perf = {}
    ok = err = 0

    for code in sorted(stocks):
        is_twse = code in twse
        print(f'  {code} ...', end=' ', flush=True)
        try:
            prices = fetch_prices(code, is_twse)
            m = calc(prices, entry_dates.get(code))
            if m:
                perf[code] = m
                parts = []
                if '5d' in m: parts.append(f'5D={m["5d"]:+.1f}%')
                if '1m' in m: parts.append(f'1M={m["1m"]:+.1f}%')
                if '3m' in m: parts.append(f'3M={m["3m"]:+.1f}%')
                if 'ma60_bias' in m: parts.append(f'60MA乖離={m["ma60_bias"]:+.1f}%')
                if 'since_ret' in m: parts.append(f'選入後={m["since_ret"]:+.1f}%')
                print('  '.join(parts) or '資料不足')
            else:
                print('資料不足')
            ok += 1
        except Exception as e:
            print(f'失敗 ({e})')
            err += 1
        time.sleep(0.3)

    print(f'\n完成：{ok} 支成功，{err} 支失敗')
    if ok == 0 or not perf:
        print('[SKIP] 沒有成功更新任何股票，保留原本的績效資料。')
        return
    final_perf = {**existing_perf, **perf}
    print('嵌入 HTML...', end=' ', flush=True)
    if embed(final_perf):
        print('完成')

if __name__ == '__main__':
    main()
