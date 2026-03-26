#!/usr/bin/env python3
"""
gspread_oauth_sync.py

Use Google OAuth (Installed App) to access a Google Sheet and update current prices.

Usage:
  1) Create OAuth client ID (Desktop) in Google Cloud, download client_secrets.json and save to ~/.openclaw/client_secrets.json
  2) Install dependencies:
       pip3 install --user gspread google-auth-oauthlib requests
  3) Run once to authorize and optionally update:
       python3 gspread_oauth_sync.py --sheet-id YOUR_SHEET_ID --update

The script stores the OAuth token at ~/.openclaw/gspread_token.json after the first run.

Notes:
 - Do NOT share client_secrets.json publicly. Keep it in ~/.openclaw/ and with mode 600.
 - The sheet must have a header row with columns: 이름, 코드, 시장, 현재가, 특이사항 (order can vary).

"""

import os
import argparse
import time
import re
import urllib.parse
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
import gspread
import requests

# Config
CLIENT_SECRETS = os.path.expanduser('~/.openclaw/client_secrets.json')
TOKEN_FILE = os.path.expanduser('~/.openclaw/gspread_token.json')
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# Simple price fetchers
HEADERS = {'User-Agent': 'Mozilla/5.0'}

def fetch_naver(code):
    try:
        url = f'https://finance.naver.com/item/main.naver?code={code}'
        r = requests.get(url, headers=HEADERS, timeout=10)
        html = r.text
        m = re.search(r'id="nowVal"[^>]*>([0-9,]+)<', html)
        if not m:
            m = re.search(r'<p class="no_today">.*?<span[^>]*class="blind"[^>]*>([0-9,]+)</span>', html, re.S)
        if m:
            return float(m.group(1).replace(',',''))
    except Exception:
        return None
    return None

def fetch_stooq(sym):
    s = sym.strip()
    s_lower = s.lower()
    candidates = [s_lower]
    if not s_lower.endswith('.us'):
        candidates = [s_lower + '.us', s_lower]
    for c in candidates:
        try:
            url = f'https://stooq.com/q/l/?s={urllib.parse.quote(c)}&f=sd2t2ohlcv&h&e=csv'
            rr = requests.get(url, timeout=10)
            txt = rr.text.strip(); lines = txt.splitlines()
            if len(lines) >= 2:
                vals = lines[1].split(',')
                if len(vals) >= 7 and vals[6] and vals[6].lower() != 'nan':
                    return float(vals[6])
        except Exception:
            continue
    return None

# Auth helpers

def get_gspread_client():
    # Load or run InstalledAppFlow
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(requests.Request())
            except Exception:
                creds = None
        if not creds:
            if not os.path.exists(CLIENT_SECRETS):
                raise FileNotFoundError(f'client_secrets.json not found at {CLIENT_SECRETS}. Create OAuth client ID (Desktop) and download client_secrets.json there.')
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS, SCOPES)
            creds = flow.run_local_server(port=0)
            # save token
            with open(TOKEN_FILE, 'w') as f:
                f.write(creds.to_json())
            os.chmod(TOKEN_FILE, 0o600)
    client = gspread.authorize(creds)
    return client

# Utility: map header names to column indices

def map_headers(row_values):
    mapping = {}
    for i, v in enumerate(row_values):
        key = v.strip()
        mapping[key] = i + 1  # gspread is 1-indexed for cells
    return mapping


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sheet-id', required=True, help='Spreadsheet ID (/d/<ID>/ in URL)')
    parser.add_argument('--update', action='store_true', help='Update the sheet with fetched prices')
    args = parser.parse_args()

    client = get_gspread_client()
    sh = client.open_by_key(args.sheet_id)
    ws = sh.sheet1

    all_rows = ws.get_all_values()
    if not all_rows:
        print('Sheet is empty')
        return
    headers = all_rows[0]
    mapping = map_headers(headers)
    required = ['이름', '코드', '시장']
    for r in required:
        if r not in mapping:
            print(f'Warning: header "{r}" not in sheet headers: {headers}')

    aktual = []
    # iterate data rows
    for ridx, row in enumerate(all_rows[1:], start=2):
        name = row[mapping.get('이름', 0)-1] if mapping.get('이름') else ''
        code = row[mapping.get('코드', 0)-1] if mapping.get('코드') else ''
        market = row[mapping.get('시장', 0)-1] if mapping.get('시장') else ''
        price = None
        source = None
        if code:
            if code.isdigit() or (market and market.upper() == 'KRX'):
                price = fetch_naver(code)
                source = 'naver'
            else:
                price = fetch_stooq(code)
                source = 'stooq'
        aktual.append({'row': ridx, 'name': name, 'code': code, 'market': market, 'price': price, 'source': source})
        print(f"Row {ridx}: {code} ({market}) -> {price} [{source}]")

        if args.update and price is not None:
            # write back to 현재가 and 특이사항 if present in header
            if '현재가' in mapping:
                try:
                    ws.update_cell(ridx, mapping['현재가'], float(round(price, 2)))
                except Exception as e:
                    print('Failed to update 현재가:', e)
            if '특이사항' in mapping:
                note = f'가격 출처: {source} (자동)'
                try:
                    ws.update_cell(ridx, mapping['특이사항'], note)
                except Exception as e:
                    print('Failed to update 특이사항:', e)
        time.sleep(0.4)

    print('\nDone. Rows processed:', len(aktual))

if __name__ == '__main__':
    main()
