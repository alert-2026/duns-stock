"""Misha & Puff early access alert (samee asked 11/18). Their VIP early-access emails (9/23 FW26, 10/21 WI26 Drop 1)
both link to /collections/preview, where the next drop sits as "Coming Soon" (sold-out price) until it opens.
So: read page 1 of that collection and alert once when items there turn buyable. Every few checks the home page
is also read, and an "early access" line appearing there is alerted once too. Run by .github/workflows/mishapuff.yml;
state in mishapuff-state.json. One page per check, so the shop is not hammered."""
import datetime, html, json, os, re, subprocess, sys, time, urllib.request

SHOP = 'https://shop.misha-and-puff.com'
PREVIEW = SHOP + '/collections/preview'
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36'
STATE = os.environ.get('MP_STATE', 'mishapuff-state.json')
KST = datetime.timezone(datetime.timedelta(hours=9))
COOLDOWN = 6 * 3600  # an opening is alerted once; a later flap within 6 hours stays quiet
HOME_EVERY = 4       # home page every 4th check
LOG = []


def log(*a):
    line = ' '.join(str(x) for x in a)
    LOG.append(line)
    print(line, flush=True)


def fetch(url):
    """Shopify answers Python's urllib with 429 from GitHub but serves curl (same as check_stock.fetch_curl)."""
    out = subprocess.run(['curl', '-sS', '--fail', '--max-time', '30', '-A', UA, url],
                         capture_output=True, timeout=40)
    if out.returncode != 0:
        raise RuntimeError('curl failed: %s' % out.stderr.decode(errors='replace').strip()[:200])
    return out.stdout.decode('utf-8', errors='replace')


def preview_items(page):
    """[(handle, name, buyable)] for the product cards of the collection page."""
    items = []
    for card in re.split(r'<li\s+class="grid__item', page)[1:]:
        h = re.search(r'href="(?:/collections/[^"/]+)?/products/([^"?#/]+)', card)
        if not h or h.group(1) == 'gift-card':
            continue
        t = (re.search(r'<h3 class="card__heading h5"\s*>\s*([^<]+?)\s*<', card)
             or re.search(r'full-unstyled-link"?[^>]*>\s*([^<]+?)\s*<', card))
        color = re.search(r'card__color-line">\s*([^<]+?)\s*<', card)
        name = html.unescape(t.group(1)) if t else h.group(1)
        if color:
            name += ' (' + html.unescape(color.group(1)) + ')'
        badges = [b.lower() for b in re.findall(r'badge--card[^>]*>\s*([^<]+?)\s*<', card)]
        buyable = 'price--sold-out' not in card and not any('coming soon' in b or 'sold out' in b for b in badges)
        items.append((h.group(1), name, buyable))
    return items


def early_access_lines(page):
    """Visible text lines on the home page that mention early access."""
    page = re.sub(r'(?is)<(script|style|noscript)\b.*?</\1>', ' ', page)
    text = html.unescape(re.sub(r'<[^>]+>', '\n', page))
    lines = {re.sub(r'\s+', ' ', l).strip() for l in text.splitlines()}
    return sorted(l for l in lines if re.search(r'early[\s-]*access|\bvip\b', l, re.I) and len(l) < 300)


def telegram(text):
    token = os.environ.get('TELEGRAM_TOKEN', '').strip()
    chats = [x.strip() for x in os.environ.get('TELEGRAM_CHAT_ID', '').split(',') if x.strip()]
    if not token or not chats:
        log('no telegram secrets; would send:', text)
        return
    for chat in chats:
        try:
            req = urllib.request.Request(f'https://api.telegram.org/bot{token}/sendMessage', json.dumps(
                {'chat_id': chat, 'text': text, 'disable_web_page_preview': True}).encode(),
                {'Content-Type': 'application/json'})
            urllib.request.urlopen(req, timeout=20).read()
        except Exception as e:
            log('telegram failed', type(e).__name__, e)


def stamp():
    n = datetime.datetime.now(KST)
    return f'{n.month}/{n.day} {n:%H:%M}, KST'


def main():
    try:
        state = json.load(open(STATE))
    except (OSError, ValueError):
        state = {}
    now = time.time()
    state['n'] = state.get('n', 0) + 1

    try:
        items = preview_items(fetch(PREVIEW))
    except Exception as e:
        items = None
        log('preview unreadable', type(e).__name__, e)
    if items:  # an empty or failed read never counts as "closed"
        buy = [(h, n) for h, n, b in items if b]
        log('preview', len(items), 'items,', len(buy), 'buyable', [n for _, n in buy[:5]])
        if buy and not state.get('open') and now - state.get('alerted', 0) > COOLDOWN:
            names = '\n'.join('• ' + n for _, n in buy[:15]) + (f'\n외 {len(buy) - 15}개' if len(buy) > 15 else '')
            telegram(f'🔔 미샤앤퍼프 얼리액세스 열림! ({stamp()})\n'
                     f'Preview 컬렉션 {len(buy)}개 구매 가능 (첫 페이지 기준)\n{names}\n{PREVIEW}')
            log('alert sent: preview open')
            state['alerted'] = now
        state['open'] = bool(buy)
    elif items is not None:
        log('preview: no product cards')

    if state['n'] % HOME_EVERY == 1:
        try:
            lines = early_access_lines(fetch(SHOP + '/'))
            log('home early-access lines', lines[:3])
            seen = set(state.get('home_lines', []))
            new = [l for l in lines if l not in seen]
            if new and now - state.get('home_alerted', 0) > COOLDOWN:
                telegram(f'🔔 미샤앤퍼프 홈페이지에 얼리액세스 안내가 떴어요 ({stamp()})\n'
                         + '\n'.join('• ' + l for l in new[:5]) + f'\n{SHOP}/\n{PREVIEW}')
                log('alert sent: home text')
                state['home_alerted'] = now
            state['home_lines'] = sorted(seen | set(lines))[-50:]
        except Exception as e:
            log('home unreadable', type(e).__name__, e)

    json.dump(state, open(STATE, 'w'), ensure_ascii=False)


if __name__ == '__main__':
    if '--test' in sys.argv:  # print what is read now, send nothing
        for h, n, b in preview_items(fetch(PREVIEW)):
            print('BUY ' if b else 'soon', n, h)
        print(early_access_lines(fetch(SHOP + '/')))
        sys.exit()
    try:
        main()
    except Exception as e:
        log('error', type(e).__name__, e)
    with open('mishapuff-log.txt', 'a') as f:
        f.write(datetime.datetime.now(KST).isoformat(timespec='seconds') + ' ' + ' | '.join(LOG) + '\n')
