"""A few single products samee is waiting for, read every few seconds on their own (samee asked 10/23:
Cuddly Bunny's Mother Earth Hood Suit, sizes 74/80 and 86/92, came back and sold again within a minute twice).
One product page per pass, so it is far lighter than a list check. Alerts look like check_stock's."""
import json
import os
import re
import time
from datetime import datetime

import check_stock as cs
import parsers

# (shop name, product page); add or remove lines here
WATCH = [
    ('커들리버니', 'https://cuddlybunny.co.kr/product/detail.html?product_no=2434'),  # Mother Earth Hood Suit - Black
]
STATE = 'state-hot.json'
EVERY = 8  # seconds between passes


def read(url):
    page = cs.fetch(url)
    icon = re.search(r"is_soldout_icon\s*=\s*'([TF])'", page)
    found = parsers.parse_sizes(page) or ([], [])
    name = re.search(r'<meta property="og:title" content="([^"]+)"', page)
    price = re.search(r'<meta property="product:price:amount" content="([\d.]+)"', page)
    return {
        'url': url, 'id': url.rsplit('=', 1)[-1],
        'name': re.sub(r'\s*-\s*cuddlybunny$', '', name.group(1).strip()) if name else url,
        'price': '{:,}원'.format(int(float(price.group(1)))) if price else '-',
        'sizes': found[0], 'sizes_out': found[1],
        # on sale only when the shop says so AND some size can be picked
        'on_sale': bool(found[0]) and not (icon and icon.group(1) == 'T'),
    }


def one_pass(state):
    for shop, url in WATCH:
        try:
            it = read(url)
        except Exception as e:  # noqa: BLE001 - try again next pass
            cs.log('hot: %s %s' % (url, e))
            continue
        old = state.get(url)
        state[url] = {k: it[k] for k in ('sizes', 'on_sale')}
        if old is None:
            continue  # first look: just remember it
        label = None
        if it['on_sale'] and not old['on_sale']:
            label = '재입고'
        elif it['on_sale'] and set(it['sizes']) - set(old['sizes']):
            label = '사이즈 재입고'
            it['new_sizes'] = [x for x in it['sizes'] if x not in old['sizes']]
        if label:
            when = datetime.now(cs.KST).strftime('%-m/%-d %H:%M')
            text = '🔔 %s · 던스스웨덴 (%s, KST)\n\n%s' % (shop, when, cs.alert_block(label, it))
            ok = cs.telegram_send(text)
            cs.log('hot: %s %s sent=%s' % (label, it['name'][:40], ok))
            if not ok:
                state[url] = old  # try again next pass


def main():
    state = cs.load_json(STATE, {})
    end = time.time() + float(os.environ.get('HOT_SECONDS', '60'))
    while time.time() < end:
        start = time.time()
        one_pass(state)
        with open(STATE, 'w') as f:
            json.dump(state, f, ensure_ascii=False)
        time.sleep(max(1, EVERY - (time.time() - start)))


if __name__ == '__main__':
    main()
