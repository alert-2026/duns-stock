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
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import parsers

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.environ.get('STATE_FILE') or os.path.join(HERE, 'state.json')
TG_CONF = os.path.join(HERE, 'telegram.json')
LOG = os.path.join(HERE, 'log.txt')
KST = timezone(timedelta(hours=9))
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36')
CHROME = os.environ.get('CHROME_PATH', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')

# (key, display name, url, parser, needs headless Chrome)
SHOPS = [
    ('gurm', '구름', 'https://gurm.kr/category/duns-sweden/70/', 'cafe24', False),
    # Gurm sometimes lists new Duns items only under NEW at first (whole shop, so Duns items are picked out)
    ('gurmnew', '구름', 'https://gurm.kr/category/new/458/', 'cafe24', False),
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
    # not a Duns shop: samee also wants Present Project's own products (whole shop)
    ('presentproject', '프레젠트프로젝트', 'https://present-project.love/20', 'imweb', False),
]
NOT_DUNS = {'presentproject'}
DUNS_ONLY = {'gurmnew'}  # shop-wide pages: keep only Duns products
IMWEB_HOSTS = {re.match(r'https?://[^/]+', s[2]).group(0) for s in SHOPS if s[3] == 'imweb'}
MAX_PAGES = 40  # list pages read per Cafe24 shop


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
    # some product links contain Korean letters, which urllib can't send as they are
    url = urllib.parse.quote(url, safe=":/?#[]@!$&'()*+,;=%~")
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': '*/*', 'Accept-Language': 'ko-KR,ko;q=0.9'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return decode(r.read(), r.headers.get('Content-Type', ''))


def fetch_sizes(url):
    """(available, sold_out) for a product link, or None. imweb loads its options separately."""
    m = re.match(r'(https?://[^/]+)/.*[?&]idx=(\d+)', url)
    if m and m.group(1) in IMWEB_HOSTS:
        req = urllib.request.Request(m.group(1) + '/shop/load_option.cm',
                                     data=('type=prod&prod_idx=' + m.group(2)).encode(),
                                     headers={'User-Agent': UA, 'X-Requested-With': 'XMLHttpRequest', 'Referer': url,
                                              'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'})
        with urllib.request.urlopen(req, timeout=30) as r:
            return parsers.parse_imweb_options(json.loads(r.read().decode('utf-8')).get('option_html') or '')
    return parsers.parse_sizes(fetch(url))


def fetch_or_none(url):
    try:
        return fetch(url)
    except Exception:  # noqa: BLE001 - the caller falls back to what it knew
        return None


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
            found = fetch_sizes(url)
        except Exception:  # noqa: BLE001 - sizes are a bonus, never block the alert
            return ''
    if not found:
        return ''
    avail, out = found
    line = '가능: ' + (', '.join(avail) if avail else '없음')
    if out:
        line += ' (품절: %s)' % ', '.join(out)
    return line + '\n'


def get_sizes(it):
    """(available, sold_out) size lists, or None when the shop doesn't show sizes."""
    if 'sizes' in it:
        return it['sizes'], it.get('sizes_out', [])
    try:
        return fetch_sizes(it['url'])
    except Exception:  # noqa: BLE001 - sizes are a bonus, never block the alert
        return None


def alert_block(label, it):
    """Same lines for every shop (layout samee approved 2026-10-16)."""
    found = get_sizes(it)
    avail, out = found or ([], [])
    # a whole-item restock or a new item: every size on sale now has just come in
    new = [x for x in it.get('new_sizes', []) if x != '전체'] or (avail if label in ('재입고', '신상') else [])
    had = [x for x in avail if x not in new]
    lines = ['[%s] %s' % (label, it['name']), '가격: ' + it['price'],
             '❤️ 신규 : ' + (', '.join(new) if new else '(사이즈 정보 없음)')]
    # every message has the same lines; '-' when a line has nothing (✅ for a whole restock or a new item)
    lines.append('✅ 가능 사이즈 : ' + (', '.join(had) or '-'))
    lines.append('❌ 품절 : ' + (', '.join(out) or '-'))
    return '\n'.join(lines + [it['url']])


PAGED = ('cafe24', 'littleluna', 'bbambam', 'coupleshot', 'imweb', 'sixshop')


def more_pages(page, url, kind, first, key):
    """Items on list pages 2..N (Pulev has 22 pages; restocks of older items show up there)."""
    last = MAX_PAGES
    m = re.search(r'xans-product-normalpaging(.*?)</div>', page, flags=re.S)
    if m:  # Cafe24 page links name the last page
        last = min(MAX_PAGES, max([int(n) for n in re.findall(r'[?&]page=(\d+)', m.group(1))] or [1]))
    param = 'page'
    if kind == 'sixshop':  # rendered pages are slow, so only read the pages its page buttons show
        param = 'productListPage'
        m = re.search(r'class="paginationNumbers"(.*?)</div></div>', page, flags=re.S)
        last = min(MAX_PAGES, max([int(n) for n in re.findall(r'page="(\d+)"', m.group(1))] or [1]) if m else 1)
    more, seen = [], {it['id'] for it in first}

    def page_url(n):
        return url + ('&' if '?' in url else '?') + '%s=%d' % (param, n)

    def get(u):
        # an error fails the whole shop, so nothing looks sold out by mistake
        try:
            return fetch_rendered(u, key) if kind == 'sixshop' else fetch(u)
        except OSError:  # one slow page out of many is common; try it once more
            time.sleep(3)
            return fetch_rendered(u, key) if kind == 'sixshop' else fetch(u)

    pages = {}
    if m and kind != 'sixshop' and last > 2:
        # the last page is known, so read the pages side by side (Gurm's ~40 pages in seconds, not ~40s)
        with ThreadPoolExecutor(max_workers=6) as ex:
            pages = dict(zip(range(2, last + 1), ex.map(get, [page_url(n) for n in range(2, last + 1)])))
    for n in range(2, last + 1):
        u = page_url(n)
        html = pages[n] if n in pages else get(u)
        got = [it for it in parse(kind, html, u) if it['id'] not in seen]
        if not got:  # past the last page (some shops repeat page 1 there)
            break
        for it in got:
            seen.add(it['id'])
            it['page'] = n
            more.append(it)
    return more


FORET_LIST = ('https://www.foretforet.com/shop/product_list.action.html?action_mode=get_list&page=%d'
              '&sep1=021&xcode=021&mcode=001&scode=090&type=Y&sort=manual&soldout_sort=Y&is_list_buy=0')


def foret_items(url):
    """All Foret Foret Duns items: the category page shows 12, the rest come from this JSON list (88 pages)."""
    def get(n):
        for attempt in (1, 2):
            try:
                return json.loads(fetch(FORET_LIST % n))
            except (OSError, ValueError):
                if attempt == 2:
                    raise
                time.sleep(3)
    first = get(1)
    pages = int(first.get('total_page_cnt') or 1)
    with ThreadPoolExecutor(max_workers=6) as ex:
        data = [first] + list(ex.map(get, range(2, min(pages, 120) + 1)))
    items, seen = [], set()
    for n, d in enumerate(data, 1):
        for it in parsers.parse_foret(d.get('html', ''), url):
            if it['id'] not in seen:
                seen.add(it['id'])
                it['page'] = n
                items.append(it)
    # a partial read would make the missing items look new later, so fail the shop instead
    if len(items) < 0.9 * int(first.get('total') or 0):
        raise ValueError('read %d of %s items' % (len(items), first.get('total')))
    return items


def check_shop(shop):
    key, name, url, kind, js = shop
    try:
        if kind == 'shopify':
            items, page = shopify_items(url), ''
        elif kind == 'foret':
            items, page = foret_items(url), ''
        else:
            page = fetch_rendered(url, key) if js else fetch(url)
            items = parse(kind, page, url)
            if kind in PAGED and items:
                items += more_pages(page, url, kind, items, key)
    except Exception as e:  # noqa: BLE001 - one bad shop must not stop the run
        return key, None, '%s: %s' % (type(e).__name__, e)
    if key in DUNS_ONLY:
        items = [it for it in items if 'DUNS' in it['name'].upper() or '던스' in it['name']]
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
    # several people can get the alerts: chat ids separated by commas, samee's own first
    chat_ids = [x.strip() for x in str(os.environ.get('TELEGRAM_CHAT_ID') or conf.get('chat_id') or '').split(',') if x.strip()]
    if not token or not chat_ids:
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
    for n, chat_id in enumerate(chat_ids):
        for chunk in chunks:
            data = urllib.parse.urlencode({'chat_id': chat_id, 'text': chunk,
                                           'disable_web_page_preview': 'true'}).encode()
            try:
                with urllib.request.urlopen('https://api.telegram.org/bot%s/sendMessage' % token,
                                            data=data, timeout=30) as r:
                    sent = json.load(r).get('ok', False)
            except Exception as e:  # noqa: BLE001
                # do not log the exception text: it may contain the request URL with the token
                log('telegram send failed (recipient %d): %s' % (n + 1, type(e).__name__))
                sent = False
            # only samee's own chat decides whether the alert counts as delivered, so someone who
            # blocked the bot can't make the same alert repeat every check
            if n == 0:
                ok = ok and sent
    return ok


# shops whose product pages show per-size stock; scanned only where SIZE_SCAN=1 (GitHub),
# since opening every product page each minute on the Mac would be too many requests
SIZE_SCAN_SHOPS = {'gurm', 'gurmnew', 'cuddlybunny', 'pulev', 'babybubble', 'checkanddot', 'rulii', 'coupleshot', 'foretforet', 'mimilemonde'}


def scan_sizes(results, state, shops=SIZE_SCAN_SHOPS):
    """Add 'sizes'/'sizes_out' to on-sale items of the given shops by opening their product pages."""
    jobs = []
    for key, items, err in results:
        if err or key not in shops:
            continue
        known = state.get(key) or {}
        for it in items:
            # sold-out items are caught by the regular [재입고] alert when they come back
            if not it['soldout']:
                jobs.append((it, known.get(it['id'], {})))

    def one(job):
        it, old = job
        try:
            found = fetch_sizes(it['url'])
        except Exception:  # noqa: BLE001
            found = None
        if found:
            it['sizes'], it['sizes_out'] = found
        elif 'sizes' in old:
            # page could not be read this time: keep what we knew so nothing is falsely alerted
            it['sizes'], it['sizes_out'] = old['sizes'], old.get('sizes_out', [])

    with ThreadPoolExecutor(max_workers=10) as ex:
        list(ex.map(one, jobs))
    return len(jobs)


CURRENT_SEASON = r'26AU|FALL26|AW26'


def rotate_sizes(results, state, shops, batch=60):
    """For the 30-second loop: re-read the sizes of a few on-sale items per check, oldest-read first,
    and carry the last known sizes for the rest, so a single size coming back (a cancellation) is caught
    within minutes without opening hundreds of pages every check."""
    now = datetime.now(KST).isoformat(timespec='seconds')
    jobs = []
    for key, items, err in results:
        if err or key not in shops:
            continue
        known = state.get(key) or {}
        for it in items:
            old = known.get(it['id'], {})
            if 'sizes' in old and 'sizes' not in it:
                it['sizes'], it['sizes_out'] = old['sizes'], old.get('sizes_out', [])
                it['size_checked'] = old.get('size_checked', '')
            if not it['soldout']:
                jobs.append(it)
    jobs.sort(key=lambda it: it.get('size_checked', ''))
    # this season's items sell out and come back most often: two thirds of each batch goes to them
    season = [it for it in jobs if re.search(CURRENT_SEASON, it['name'], flags=re.I)]
    picked = season[:batch * 2 // 3]
    chosen = {id(it) for it in picked}
    rest = [it for it in jobs if id(it) not in chosen]
    jobs = picked + rest[:batch - len(picked)]

    def one(it):
        try:
            found = fetch_sizes(it['url'])
        except Exception:  # noqa: BLE001 - keep the carried sizes
            found = None
        if found:
            it['sizes'], it['sizes_out'] = found
        it['size_checked'] = now

    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(one, jobs))
    return len(jobs)


def main():
    global SHOPS
    # ONLY_SHOPS / SKIP_SHOPS let the fast GitHub loop watch some shops every minute on their own
    only = set(filter(None, os.environ.get('ONLY_SHOPS', '').split(',')))
    skip = set(filter(None, os.environ.get('SKIP_SHOPS', '').split(',')))
    SHOPS = [x for x in SHOPS if (not only or x[0] in only) and x[0] not in skip]
    state = load_json(STATE, {})
    # sizes saved before 10/16 kept Cafe24's escaped slash (74\/80); fix them so they don't look like new sizes
    for shop in state.values():
        for rec in shop.values() if isinstance(shop, dict) else []:
            for f in ('sizes', 'sizes_out'):
                if isinstance(rec, dict) and isinstance(rec.get(f), list):
                    rec[f] = [x.replace('\\/', '/') for x in rec[f]]
    # every shop at once, so a check takes as long as the slowest shop (about 20s), not the sum
    with ThreadPoolExecutor(max_workers=max(1, len(SHOPS))) as ex:
        results = list(ex.map(check_shop, SHOPS))
    if os.environ.get('SIZE_SCAN') == '1':
        log('size scan: %d product pages' % scan_sizes(results, state))
    # small shops whose sizes are cheap to read: every item, every check
    every = set(filter(None, os.environ.get('SIZE_EVERY_SHOPS', '').split(',')))
    if every:
        log('sizes every check: %d items' % scan_sizes(results, state, every))
    rotate = set(filter(None, os.environ.get('ROTATE_SIZE_SHOPS', '').split(',')))
    if rotate:
        log('rotating size scan: %d product pages' % rotate_sizes(results, state, rotate))

    names = {s[0]: s[1] for s in SHOPS}
    kinds = {s[0]: s[3] for s in SHOPS}
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
        # shops the 30-second loop already watches (sizes included): this run only keeps its record up to date
        learn_only = key in set(filter(None, os.environ.get('LEARN_ONLY_SHOPS', '').split(',')))
        # pages 2..N were read from 2026-10-12; until a shop's later pages are known, learn them quietly
        # (those items were already for sale, so they must not all arrive as new items)
        quiet = not any(isinstance(v, dict) and v.get('page', 1) > 1 for v in known.values())
        if kinds[key] in ('cafe24', 'littleluna'):
            # Cafe24 caches each list page on its own and the order shifts, so the same item can look sold out
            # on one page and on sale on another: when the list disagrees with what we knew, ask its own page
            flips = [it for it in items if known.get(it['id']) and bool(known[it['id']].get('soldout')) != it['soldout']]
            with ThreadPoolExecutor(max_workers=8) as ex:
                pages = list(ex.map(fetch_or_none, [it['url'] for it in flips[:40]])) + [None] * len(flips[40:])
            for it, page in zip(flips, pages):
                m = re.search(r"is_soldout_icon\s*=\s*'([TF])'", page or '')
                if not m:  # can't tell: keep what we knew
                    it['soldout'] = bool(known[it['id']].get('soldout'))
                    continue
                it['soldout'] = m.group(1) == 'T'
                found = parsers.parse_sizes(page)
                if found:
                    it['sizes'], it['sizes_out'] = found
        # some shops list an item as on sale while every size is sold out: that can't be bought,
        # so items about to be alerted get their sizes read first (side by side, at most 40 per shop)
        maybe = [it for it in items if not it['soldout'] and not (quiet and it.get('page', 1) > 1)
                 and (known.get(it['id']) is None or known[it['id']].get('soldout'))]
        with ThreadPoolExecutor(max_workers=8) as ex:
            found_all = list(ex.map(get_sizes, maybe[:40])) + [None] * len(maybe[40:])
        for it, found in zip(maybe, found_all):
            if found:
                it['sizes'], it['sizes_out'] = found
                it['soldout'] = it['size_soldout'] = not found[0]
            elif (known.get(it['id']) or {}).get('size_soldout'):
                # its sizes were all sold out last time and couldn't be read now: don't call it a restock
                it['soldout'] = it['size_soldout'] = True
        for it in items:
            old = known.get(it['id'])
            # only things that can be bought now are alerted (samee buys restocks / cancellations)
            if old is None:
                if (quiet and it.get('page', 1) > 1) or learn_only:
                    pass
                elif not it['soldout']:
                    changes.append(('신상', names[key], it))
                    n_changes += 1
            elif old.get('soldout') and not it['soldout'] and not learn_only:
                changes.append(('재입고', names[key], it))
                n_changes += 1
            elif 'sizes' in old and not learn_only and set(it.get('sizes', [])) - set(old['sizes']):
                # a size came back on an item that was already partly on sale
                it['new_sizes'] = [x for x in it['sizes'] if x not in old['sizes']]
                changes.append(('사이즈 재입고', names[key], it))
                n_changes += 1
            known[it['id']] = {k: v for k, v in dict(it, last_seen=now).items() if k != 'new_sizes'}
        summary.append('%s:%d%s' % (key, len(items), ('/+%d' % n_changes) if n_changes else ''))

    # ALERT_LABELS: the 5-minute size loop only sends [사이즈 재입고]; the 1-minute loop sends the rest
    labels = set(filter(None, os.environ.get('ALERT_LABELS', '').split(',')))
    if labels:
        changes = [c for c in changes if c[0] in labels]

    # Gurm's Duns and NEW lists are cached separately, so one restock can show up a run apart on each:
    # don't send the same alert for the same product again within 5 minutes
    recent = {k: t for k, t in state.get('_recent', {}).items() if time.time() - t < 300}
    fresh = []
    for c in changes:
        label, shop, it = c
        k = '%s|%s|%s|%s' % (label, shop, it['id'], ','.join(it.get('new_sizes', [])))
        if k in recent:
            log('  already alerted: %s %s %s' % (label, shop, it['name'][:40]))
            continue
        recent[k] = time.time()
        fresh.append(c)
    changes = fresh
    state['_recent'] = recent

    if changes:
        order = {'재입고': 0, '사이즈 재입고': 0, '신상': 1, '품절': 2}
        changes.sort(key=lambda c: order[c[0]])
        when = datetime.now(KST).strftime('%-m/%-d %H:%M')
        by_shop = {}
        shop_keys = {s[1]: s[0] for s in SHOPS}
        # read sizes for the alerts side by side (one page each), so many alerts at once can't stall the check
        with ThreadPoolExecutor(max_workers=8) as ex:
            need = [it for _, _, it in changes if 'sizes' not in it]
            for it, found in zip(need, ex.map(get_sizes, need)):
                if found:
                    it['sizes'], it['sizes_out'] = found
        shown = set()
        for label, shop, it in changes:
            # Coco & Jennie is watched on two category pages that share products: show each once
            # (Gurm's Duns and NEW pages also share products, under different links)
            if (shop, it['id']) in shown:
                continue
            shown.add((shop, it['id']))
            by_shop.setdefault(shop, []).append(alert_block(label, it))
        # one Telegram message per shop (samee asked for this on 2026-10-10)
        sent = True
        for shop, blocks in by_shop.items():
            head = ('🔔 %s (%s, KST)' if shop_keys[shop] in NOT_DUNS else '🔔 %s · 던스스웨덴 (%s, KST)') % (shop, when)
            sent = telegram_send('\n\n'.join([head] + blocks)) and sent
        log('changes=%d sent=%s' % (len(changes), sent))
        for label, shop, it in changes:
            log('  %s %s %s %s' % (label, shop, it['id'], it['name'][:40]))
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
