Notion calls disabled by user flag (~/.openclaw/NOTION_DISABLED). Exiting.
#!/usr/bin/env python3
import json
import time
import urllib.request
import urllib.parse

# Load config
with open('/Users/hyereekim/.openclaw/openclaw.json','r') as f:
    cfg=json.load(f)
NOTION_TOKEN=cfg.get('notion',{}).get('token')
TELEGRAM_TOKEN=cfg.get('channels',{}).get('telegram',{}).get('botToken')
TELEGRAM_CHAT_ID='5916010286'  # your telegram id

DB_ID='38ba6bde-992d-41d9-993f-6a8128e12a35'
NOTION_HEADERS={
    'Authorization': f'Bearer {NOTION_TOKEN}',
    'Notion-Version': '2025-09-03',
    'Content-Type': 'application/json'
}

# Helper to do Notion requests
def notion_request(path, method='GET', data=None):
    url='https://api.notion.com/v1'+path
    req=urllib.request.Request(url, method=method)
    for k,v in NOTION_HEADERS.items():
        req.add_header(k,v)
    if data is not None:
        body=json.dumps(data).encode('utf-8')
        req.data=body
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except Exception as e:
        print('Notion request failed', e)
        return None

# Query database: for API version here, query data_source instead of /databases/{db}/query
def query_database(db_id):
    # get database metadata to find data_source id
    meta = notion_request(f'/databases/{db_id}')
    if not meta:
        return None
    ds = None
    ds_list = meta.get('data_sources') or []
    if len(ds_list) > 0:
        ds = ds_list[0].get('id')
    if not ds:
        print('No data_source found for DB')
        return None
    # now call data_sources query endpoint
    return notion_request(f'/data_sources/{ds}/query', method='POST', data={})

def patch_page(page_id, properties):
    return notion_request(f'/pages/{page_id}', method='PATCH', data={'properties':properties})

def send_telegram(text):
    if not TELEGRAM_TOKEN: return
    data = urllib.parse.urlencode({'chat_id': TELEGRAM_CHAT_ID, 'text': text})
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    try:
        req=urllib.request.Request(url, data=data.encode('utf-8'))
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read()
    except Exception as e:
        print('tg send failed', e)

def yf_symbol(ticker):
    # if 6 digit numeric assume KRX
    if ticker.isdigit() and len(ticker)==6:
        return ticker + '.KS'
    return ticker


def fetch_yahoo_quote(symbol):
    url=f'https://query1.finance.yahoo.com/v7/finance/quote?symbols={urllib.parse.quote(symbol)}'
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data=json.load(r)
            q=data.get('quoteResponse',{}).get('result',[{}])[0]
            return q
    except Exception as e:
        print('yahoo fetch failed', symbol, e)
        return None

ALERT_PCT=3.0

def extract_prop_text(prop):
    # handle Notion title/rich_text
    if not prop: return ''
    if 'title' in prop:
        arr=prop['title']
    elif 'rich_text' in prop:
        arr=prop['rich_text']
    else:
        return ''
    texts=[t.get('plain_text','') for t in arr]
    return ''.join(texts)


def main_loop():
    print('starting monitor loop')
    while True:
        db=query_database(DB_ID)
        if not db:
            print('db query failed, sleeping')
            time.sleep(60)
            continue
        results=db.get('results',[])
        for page in results:
            pid=page.get('id')
            props=page.get('properties',{})
            ticker=extract_prop_text(props.get('Ticker'))
            notify = False
            if '알림수신' in props:
                notify = props.get('알림수신',{}).get('checkbox', False)
            if not ticker:
                continue
            sym=yf_symbol(ticker.strip())
            q=fetch_yahoo_quote(sym)
            if not q:
                continue
            current=q.get('regularMarketPrice') or q.get('currentPrice')
            prev=q.get('regularMarketPreviousClose')
            change_pct=None
            vol=q.get('regularMarketVolume')
            if current is not None and prev is not None and prev!=0:
                change_pct = (current - prev)/prev*100.0
            alerts=[]
            if change_pct is not None and abs(change_pct) >= ALERT_PCT:
                alerts.append(f'등락률 {change_pct:.2f}%')
            # 52 week high check
            if q.get('fiftyTwoWeekHigh') and current is not None and current >= q.get('fiftyTwoWeekHigh'):
                alerts.append('52주 최고가 갱신')
            # prepare properties update
            properties={}
            if current is not None:
                properties['현재가']={'number': round(current,2)}
            if prev is not None:
                properties['전일종가']={'number': round(prev,2)}
            if change_pct is not None:
                properties['등락률']={'number': round(change_pct/100.0, 4)}
            if vol is not None:
                properties['거래량']={'number': int(vol)}
            properties['마지막체크']={'date':{'start': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}}
            patch_page(pid, properties)
            # notify
            if notify and alerts:
                title=extract_prop_text(props.get('종목명')) or ticker
                msg=f"[{title}] ({ticker}) 현재가: {current} 전일: {prev} 변동: {change_pct:.2f}% 이유: {', '.join(alerts)}\nNotion: https://www.notion.so/{DB_ID}"
                send_telegram(msg)
        # sleep 300s
        time.sleep(300)

if __name__=='__main__':
    main_loop()
