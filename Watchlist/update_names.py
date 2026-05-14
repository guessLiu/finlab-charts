"""
執行一次，從 TWSE/TPEX 抓取股票名稱，並從本地 stock_categories.json 嵌入分類。
之後 HTML 完全離線運作，不需要網路也能顯示名稱與分類。
"""
import json, re, sys
from pathlib import Path
import urllib.request

# 強制終端機用 UTF-8，避免 Windows cp950 編碼錯誤
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

TWSE_URLS = [
    'https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL',
    'https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_d',   # 備援
]
TPEX_URL = 'https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes'
CATEGORIES_PATH = Path(__file__).parent / 'stock_categories.json'

def get_json(url, timeout=30):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))

def fetch_twse():
    for url in TWSE_URLS:
        try:
            print(f'抓取 TWSE ({url.split("/")[-1]})...', end=' ', flush=True)
            data  = get_json(url)
            lst   = data if isinstance(data, list) else data.get('data', [])
            codes, names = [], {}
            for d in lst:
                code = d.get('Code', '').strip()
                name = d.get('Name', '').strip()
                if code:
                    codes.append(code)
                    if name:
                        names[code] = name
            if codes:
                print(f'{len(codes)} 支')
                return codes, names
            print('空回應，嘗試備援...')
        except Exception as e:
            print(f'失敗 ({e})，嘗試備援...')
    return [], {}

def fetch_tpex():
    print('抓取 TPEX 上櫃...', end=' ', flush=True)
    data = get_json(TPEX_URL)
    lst  = data if isinstance(data, list) else data.get('data', [])
    names, cnt = {}, 0
    for d in lst:
        code = (d.get('Code') or d.get('SecuritiesCompanyCode') or '').strip()
        name = (d.get('Name') or d.get('CompanyName') or '').strip()
        if code and name:
            names[code] = name
            cnt += 1
    print(f'{cnt} 支')
    return names

def build_categories(all_names):
    try:
        with open(CATEGORIES_PATH, encoding='utf-8-sig') as f:
            local_categories = json.load(f)
    except Exception as e:
        print(f'[WARN] 無法讀取本地分類檔 {CATEGORIES_PATH.name}，略過分類嵌入：{e}')
        return {}

    categories = {
        code: local_categories[code]
        for code in all_names
        if code in local_categories and local_categories[code]
    }

    print(f'本地分類資料 {len(categories)} 支')
    return categories

def embed(twse_codes, all_names, categories):
    html_path = Path(__file__).parent / 'stock_watchlist.html'
    if not html_path.exists():
        print(f'找不到 {html_path}')
        return False

    content    = html_path.read_text(encoding='utf-8')
    names_json      = json.dumps(all_names,   ensure_ascii=False, separators=(',', ':'))
    categories_json = json.dumps(categories,  ensure_ascii=False, separators=(',', ':'))
    codes_json      = json.dumps(twse_codes,  ensure_ascii=False, separators=(',', ':'))

    new_block = (
        '/* __STOCK_NAMES__ */\n'
        f'let stockNames = {names_json};\n'
        f'let stockCategories = {categories_json};\n'
        f'let embeddedTWSECodes = {codes_json};\n'
        '/* __STOCK_NAMES_END__ */'
    )

    pattern = r'/\* __STOCK_NAMES__ \*/[\s\S]*?/\* __STOCK_NAMES_END__ \*/'
    if not re.search(pattern, content):
        print('找不到 HTML 標記區塊，請確認 HTML 版本正確')
        return False

    updated = re.sub(
        pattern,
        new_block,
        content
    )

    if updated == content:
        print('資料無變化，略過寫入')
        return True

    html_path.write_text(updated, encoding='utf-8')
    return True

def main():
    print('=== 更新股票名稱 ===\n')
    all_names  = {}
    twse_codes = []

    try:
        twse_codes, twse_names = fetch_twse()
        all_names.update(twse_names)
    except Exception as e:
        print(f'TWSE 全部失敗: {e}')

    try:
        tpex_names = fetch_tpex()
        all_names.update(tpex_names)
    except Exception as e:
        print(f'TPEX 失敗: {e}')

    if not all_names:
        print('\n[FAIL] 未能抓到任何資料，請確認網路連線')
        sys.exit(1)

    categories = build_categories(all_names)

    print(f'\n合計 {len(all_names)} 支股票，嵌入 HTML...', end=' ', flush=True)
    if embed(twse_codes, all_names, categories):
        print('完成')
        print('\n[OK] 重新開啟 stock_watchlist.html 即可看到股票名稱')
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()
