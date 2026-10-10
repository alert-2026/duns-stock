#!/usr/bin/env python3
"""Duns Sweden stock watcher: checks shop list pages and sends Telegram alerts on changes.

First run (or the first successful parse of a shop) only records a baseline.
Standard library only. The Telegram token is read from telegram.json and never printed or logged.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import parsers

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, 'state.json')
TG_CONF = os.path.join(HERE, 'telegram.json')
LOG = os.path.join(HERE, 'log.txt')
KST = timezone(timedelta(hours=9))
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36')
CHROME = os.environ.get('CHROME_PATH', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')

# (key, display name, url, parser, needs headless Chrome)
SHOPS = [
    ('gurm', '구름', 'https://gurm.kr/category/duns-sweden/70/', 'cafe24', False),
    ('cuddlybunny', '커들리버니', 'https://cuddlybunny.co.kr/category/duns-sweden/72', 'cafe24', False),
    ('pulev', '풀레브', 'https://pulev.co.kr/category/duns%EB%8D%98%EC%8A%A4/620/', 'cafe24', False),
    ('babybubble', '베이비버블', 'https://babybubble.co.kr/category/duns/179/', 'cafe24', False),
    ('bbambam', '빰밤', 'http://www.bbambam.com/m/product_list.html?mcode=083&type=M&xcode=034', 'bbambam', False),
    ('checkanddot', '체크앤도트', 'https://checkanddot.com/category/duns-sweden/488/', 'cafe24', False),
    ('dearmykiz', '디어마이키즈', 'https://dearmykiz.com/category/duns-sweden/235/', 'cafe24', False),
    ('littleluna', '리틀루나', 'https://littleluna.co.kr/category/duns-sweden%EB%8D%98%EC%8A%A4-%EC%8A%A4%EC%9B%A8%EB%8D%B4/216/', 'littleluna', False),
    ('coupleshot', '미니커플샷', 'http://www.coupleshot.com/shop/shopbrand.html?xcode=054&type=X', 'coupleshot', False),
    ('rulii', '루리샵', 'https://m.rulii.co.kr/category/$1/338', 'cafe24', False),
    ('mimilemonde', '미미르몽드', 'https://mimilemonde.com/39', 'imweb', False),
    ('foretforet', '포레포레', 'https://www.foretforet.com/shop/shopbrand.html?xcode=021&mcode=001&scode=090&type=Y', 'foret', True),
    ('coconjennie', '코코앤제니', 'https://coconjennie.com/untitled-31', 'sixshop', True),
    ('coconjennie2', '코코앤제니', 'https://coconjennie.com/untitled-52', 'sixshop', True),
    ('blingandon', '블링앤온', 'https://www.blingandon.com/dunssweden', 'sixshop', True),
    ('official', '던스 공식몰', 'https://shopdunssweden.se', 'shopify', False),
    ('mnkl', '엠엔케이엘', 'https://mnkl.co.kr/category/duns-sweden/254/', 'cafe24', False),
    ('happylittleattic', '해피리틀애틱', 'https://happylittleattic.com/collections/duns-sweden', 'shopify', False),
]


def log(msg):
    line = '%s %s\n' % (datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S'), msg)
    try:
        if os.path.exists(LOG) and os.path.getsize(LOG) > 1_000_000:
            os.replace(LOG, LOG + '.old')
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(line)
    except OSError:
        pass
    sys.stdout.write(line)


def decode(raw, content_type=''):
    m = re.search(r'charset=([\w-]+)', content_type or '', flags=re.I) \
        or re.search(rb'charset=["\']?([\w-]+)', raw[:3000], flags=re.I)
    cs = m.group(1) if m else 'utf-8'
    cs = cs.decode() if isinstance(cs, bytes) else cs
    if cs.lower() in ('euc-kr', 'ks_c_5601-1987'):
        cs = 'cp949'
    try:
        return raw.decode(cs)
    except (UnicodeDecodeError, LookupError):
        try:
            return raw.decode('utf-8')
        except UnicodeDecodeError:
            return raw.decode('cp949', errors='replace')


def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': '*/*', 'Accept-Language': 'ko-KR,ko;q=0.9'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return decode(r.read(), r.headers.get('Content-Type', ''))


def fetch_curl(url):
    """Shopify answers Python's urllib with 429 but serves curl, so use curl there."""
    out = subprocess.run(['curl', '-sS', '--fail', '--max-time', '30', '-A', UA, url],
                         capture_output=True, timeout=40)
    if out.returncode != 0:
        raise RuntimeError('curl failed: %s' % out.stderr.decode(errors='replace').strip()[:200])
    return out.stdout.decode('utf-8', errors='replace')


def fetch_rendered(url, key):
    """Render a JS page with the installed Google Chrome (separate throwaway profile)."""
    if not os.path.exists(CHROME):
        raise RuntimeError('Google Chrome not found')
    profile = os.path.join(tempfile.gettempdir(), 'duns-stock-chrome-' + key)
    p = subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
                          '--no-default-browser-check', '--user-data-dir=' + profile,
                          '--user-agent=' + UA, '--virtual-time-budget=15000', '--dump-dom', url],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    # headless Chrome often keeps running after dumping the DOM, so stop reading at </html>
    timer = threading.Timer(45, p.kill)
    timer.start()
    out = b''
    try:
        for chunk in iter(lambda: p.stdout.read1(65536), b''):
            out += chunk
            if out.rstrip().endswith(b'</html>'):
                break
    finally:
        timer.cancel()
        p.kill()
        p.wait()
    return out.decode('utf-8', errors='replace')


def parse(kind, page, url):
    if kind == 'cafe24':
        return parsers.parse_cafe24(page, url)
    if kind == 'littleluna':
        # its skin prints a "SOLD OUT" span on every item (shown via CSS), so only icons count
        return parsers.parse_cafe24(page, url, class_marker=False)
    return getattr(parsers, 'parse_' + kind)(page, url)


def shopify_items(base):
    """All products of a Shopify shop via its public products.json (sizes included)."""
    items = []
    for page in range(1, 11):
        data = json.loads(fetch_curl('%s/products.json?limit=250&page=%d' % (base, page)))
        got = parsers.parse_shopify(data, base)
        items += got
        if len(data.get('products', [])) < 250:
            break
    return items


def size_line(url, it=None):
    """'가능: 80, 86 (품절: 74)' line for an alert, or '' when sizes can't be read."""
    if it and 'sizes' in it:
        found = it['sizes'], it.get('sizes_out', [])
    else:
        try:
            found = parsers.parse_sizes(fetch(url))
        except Exception:  # noqa: BLE001 - sizes are a bonus, never block the alert
            return ''
    if not found:
        return ''
    avail, out = found
    line = '가능: ' + (', '.join(avail) if avail else '없음')
    if out:
        line += ' (품절: %s)' % ', '.join(out)
    return line + '\n'


def check_shop(shop):
    key, name, url, kind, js = shop
    try:
        if kind == 'shopify':
            items, page = shopify_items(url), ''
        else:
            page = fetch_rendered(url, key) if js else fetch(url)
            items = parse(kind, page, url)
    except Exception as e:  # noqa: BLE001 - one bad shop must not stop the run
        return key, None, '%s: %s' % (type(e).__name__, e)
    if not items:
        return key, None, 'parsed 0 products (%d bytes)' % len(page)
    return key, items, None


def load_json(path, default):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_state(state):
    tmp = STATE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE)


def telegram_send(text):
    conf = load_json(TG_CONF, {})
    # GitHub Actions passes these as secrets; on the Mac they come from telegram.json
    token = (os.environ.get('TELEGRAM_TOKEN') or conf.get('token') or '').strip()
    chat_id = str(os.environ.get('TELEGRAM_CHAT_ID') or conf.get('chat_id') or '').strip()
    if not token or not chat_id:
        log('telegram not configured; message not sent')
        return False
    ok = True
    # Telegram limit is 4096 chars; split on blank lines between entries
    chunks, cur = [], ''
    for part in text.split('\n\n'):
        if len(cur) + len(part) + 2 > 3900 and cur:
            chunks.append(cur)
            cur = ''
        cur = (cur + '\n\n' + part) if cur else part
    chunks.append(cur)
    for chunk in chunks:
        data = urllib.parse.urlencode({'chat_id': chat_id, 'text': chunk,
                                       'disable_web_page_preview': 'true'}).encode()
        try:
            with urllib.request.urlopen('https://api.telegram.org/bot%s/sendMessage' % token,
                                        data=data, timeout=30) as r:
                ok = ok and json.load(r).get('ok', False)
        except Exception as e:  # noqa: BLE001
            # do not log the exception text: it may contain the request URL with the token
            log('telegram send failed: %s' % type(e).__name__)
            ok = False
    return ok


# shops whose product pages show per-size stock; scanned only where SIZE_SCAN=1 (GitHub),
# since opening every product page each minute on the Mac would be too many requests
SIZE_SCAN_SHOPS = {'gurm', 'cuddlybunny', 'pulev', 'babybubble', 'checkanddot', 'rulii', 'coupleshot', 'foretforet'}


def scan_sizes(results, state):
    """Add 'sizes'/'sizes_out' to on-sale items of SIZE_SCAN_SHOPS by opening their product pages."""
    jobs = []
    for key, items, err in results:
        if err or key not in SIZE_SCAN_SHOPS:
            continue
        known = state.get(key) or {}
        for it in items:
            # sold-out items are caught by the regular [재입고] alert when they come back
            if not it['soldout']:
                jobs.append((it, known.get(it['id'], {})))

    def one(job):
        it, old = job
        try:
            found = parsers.parse_sizes(fetch(it['url']))
        except Exception:  # noqa: BLE001
            found = None
        if found:
            it['sizes'], it['sizes_out'] = found
        elif 'sizes' in old:
            # page could not be read this time: keep what we knew so nothing is falsely alerted
            it['sizes'], it['sizes_out'] = old['sizes'], old.get('sizes_out', [])

    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(one, jobs))
    return len(jobs)


def main():
    state = load_json(STATE, {})
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(check_shop, SHOPS))
    if os.environ.get('SIZE_SCAN') == '1':
        log('size scan: %d product pages' % scan_sizes(results, state))

    names = {s[0]: s[1] for s in SHOPS}
    changes = []
    summary = []
    for key, items, err in results:
        if err:
            log('SKIP %s (%s): %s' % (key, names[key], err))
            summary.append('%s:skip' % key)
            continue
        known = state.get(key)
        now = datetime.now(KST).isoformat(timespec='seconds')
        if known is None:
            state[key] = {i['id']: dict(i, last_seen=now) for i in items}
            summary.append('%s:%d(baseline)' % (key, len(items)))
            continue
        n_changes = 0
        for it in items:
            old = known.get(it['id'])
            # only things that can be bought now are alerted (samee buys restocks / cancellations)
            if old is None:
                if not it['soldout']:
                    changes.append(('신상', names[key], it))
                    n_changes += 1
            elif old.get('soldout') and not it['soldout']:
                changes.append(('재입고', names[key], it))
                n_changes += 1
            elif 'sizes' in old and set(it.get('sizes', [])) - set(old['sizes']):
                # a size came back on an item that was already partly on sale
                it['new_sizes'] = [x for x in it['sizes'] if x not in old['sizes']]
                changes.append(('사이즈 재입고', names[key], it))
                n_changes += 1
            known[it['id']] = {k: v for k, v in dict(it, last_seen=now).items() if k != 'new_sizes'}
        summary.append('%s:%d%s' % (key, len(items), ('/+%d' % n_changes) if n_changes else ''))

    if changes:
        order = {'재입고': 0, '사이즈 재입고': 0, '신상': 1, '품절': 2}
        changes.sort(key=lambda c: order[c[0]])
        when = datetime.now(KST).strftime('%-m/%-d %H:%M')
        by_shop = {}
        for label, shop, it in changes:
            extra = ' (품절)' if label == '신상' and it['soldout'] else ''
            line2 = it['name'] + (' · ' + it['price'] if it['price'] else '') + extra
            sizes = size_line(it['url'], it) if label != '품절' else ''
            if it.get('new_sizes'):
                sizes = '새로 들어온 사이즈: %s\n%s' % (', '.join(it['new_sizes']), sizes)
            by_shop.setdefault(shop, []).append('[%s] %s\n%s%s' % (label, line2, sizes, it['url']))
        # one Telegram message per shop (samee asked for this on 2026-10-10)
        sent = True
        for shop, blocks in by_shop.items():
            head = '🔔 %s · 던스스웨덴 (%s, KST)' % (shop, when)
            sent = telegram_send('\n\n'.join([head] + blocks)) and sent
        log('changes=%d sent=%s' % (len(changes), sent))
        if not sent:
            # keep the previous state so the same changes are retried next run
            log('state not saved because the alert was not delivered')
            log('run: ' + ' '.join(summary))
            return
    save_state(state)
    log('run: ' + ' '.join(summary))


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--size-test':
        # print the sizes read from the first product of each shop (no alerts, no state change)
        for key, items, err in map(check_shop, SHOPS):
            if err or not items:
                log('SIZE %s: skip (%s)' % (key, err))
                continue
            for it in items[:3]:
                log('SIZE %s: %s | %s' % (key, it['name'][:40], size_line(it['url'], it).strip() or 'unknown'))
                if 'sizes' not in it:
                    os.makedirs('pages', exist_ok=True)
                    try:
                        body = fetch(it['url'])
                        log('PAGE %s %d bytes %s' % (key, len(body), it['url']))
                        with open('pages/%s-%s.html' % (key, it['id']), 'w', encoding='utf-8') as f:
                            f.write(body)
                    except Exception:  # noqa: BLE001
                        pass
    elif len(sys.argv) > 1 and sys.argv[1] == '--test-message':
        print('sent' if telegram_send('던스스웨덴 재고 알림이 연결됐어요') else 'failed')
    else:
        main()
