"""Shop list-page parsers. Each returns a list of dicts: {id, name, price, url, soldout}."""
import html as htmllib
import json
import re
from urllib.parse import urljoin

PRICE_RE = re.compile(r'(?:KRW\s*(\d{1,3}(?:,\d{3})+|\d+))|(?:(\d{1,3}(?:,\d{3})+|\d+)\s*원)')


def clean(fragment):
    t = re.sub(r'<br\s*/?>', ' ', fragment, flags=re.I)
    t = re.sub(r'<[^>]+>', ' ', t)
    t = htmllib.unescape(t)
    return re.sub(r'\s+', ' ', t).strip()


def first_price(fragment):
    frag = re.sub(r'<strike>.*?</strike>', ' ', fragment, flags=re.S | re.I)
    frag = re.sub(r'<(\w+)[^>]*class="[^"]*(?:custom|consumer)[^"]*"[^>]*>.*?</\1>', ' ', frag, flags=re.S | re.I)
    for m in PRICE_RE.finditer(clean(frag)):
        num = m.group(1) or m.group(2)
        if num.replace(',', '').strip('0'):
            return num + '원'
    return ''


def has_soldout(block, class_marker=True):
    # image icon (cafe24 default ico_product_soldout.gif, or a custom icon with alt="품절")
    for img in re.findall(r'<img[^>]*>', block, flags=re.I):
        if re.search(r'soldout|sold_out|품절', img, flags=re.I) and 'displaynone' not in img:
            return True
    if not class_marker:
        return False
    # element with a soldout class that is visible and has text / child markup
    for m in re.finditer(r'<(\w+)[^>]*class="([^"]*sold_?out[^"]*)"[^>]*>(.*?)</\1>', block, flags=re.S | re.I):
        cls, inner = m.group(2), m.group(3)
        if 'displaynone' in cls:
            continue
        if inner.strip():
            return True
    return False


# ---------------------------------------------------------------- Cafe24
def parse_cafe24(page, base, class_marker=True):
    s = re.sub(r'<!--.*?-->', '', page, flags=re.S)
    starts = [m.start() for m in re.finditer(r'class="xans-element- xans-product xans-product-listnormal', s)]
    if not starts:
        return []
    anchor = -1
    for key in ('xans-product-normalpackage', 'xans-product-orderby', 'Product_ListMenu'):
        anchor = s.find(key)
        if anchor >= 0:
            break
    after = [x for x in starts if x > anchor] if anchor >= 0 else []
    start = after[0] if after else starts[0]
    nxt = [x for x in starts if x > start]
    ends = [i for i in (s.find('xans-product-normalpaging', start), nxt[0] if nxt else -1) if i > 0]
    region = s[start:min(ends)] if ends else s[start:start + 400000]
    # flatten nested spec lists (they contain <li class="xans-record-"> too)
    region = re.sub(r'<ul[^>]*xans-product-listitem[^>]*>(.*?)</ul>',
                    lambda m: '<div class="spec-flat">' + m.group(1).replace('<li', '<div').replace('</li>', '</div>') + '</div>',
                    region, flags=re.S)
    parts = re.split(r'(?=<li\b[^>]*xans-record-)', region)
    items, seen = [], set()
    for blk in parts[1:]:
        m = (re.search(r'href="([^"]*/product/[^"]*?/(\d+)/category/[^"]*)"', blk)
             or re.search(r'href="([^"]*product_no=(\d+)[^"]*)"', blk))
        if not m:
            continue
        pid = m.group(2)
        if pid in seen:
            continue
        seen.add(pid)
        name = ''
        nm = re.search(r'class="[^"]*\bname\b[^"]*"[^>]*>.*?<a\b[^>]*>(.*?)</a>', blk, flags=re.S)
        if nm:
            frag = re.sub(r'<span class="title displaynone">.*?</span>\s*:\s*</span>', '', nm.group(1), flags=re.S)
            name = clean(frag)
        if not name:
            alt = re.search(r'<img[^>]*alt="([^"]+)"', blk)
            name = clean(alt.group(1)) if alt else pid
        items.append({
            'id': pid,
            'name': name,
            'price': first_price(blk),
            'url': urljoin(base, htmllib.unescape(m.group(1))),
            'soldout': has_soldout(blk, class_marker),
        })
    return items


# ---------------------------------------------------------------- MakeShop
def _makeshop_price(blk):
    frag = re.sub(r'<strike>.*?</strike>', ' ', blk, flags=re.S | re.I)
    for cls in ('price', 'mk_price'):
        for m in re.finditer(r'<span class="%s">\s*([\d,]+)\s*(원)?\s*</span>' % cls, frag):
            if m.group(1).replace(',', '').strip('0'):
                return m.group(1) + '원'
    return first_price(blk)


def _makeshop_soldout(blk):
    if has_soldout(blk):
        return True
    price_area = re.search(r'class="[^"]*(?:price)[^"]*"[^>]*>(.*?)</(?:div|p|td)>', blk, flags=re.S)
    return bool(price_area and re.search(r'품절|sold\s*out', clean(price_area.group(1)), flags=re.I))


def parse_makeshop(page, base, split_re, name_re):
    items, seen = [], set()
    for blk in re.split(split_re, page)[1:]:
        m = re.search(r'href=["\']?([^"\'\s>]*branduid=(\d+)[^"\'\s>]*)', blk)
        if not m or m.group(2) in seen:
            continue
        seen.add(m.group(2))
        nm = re.search(name_re, blk, flags=re.S)
        name = clean(nm.group(1)) if nm else m.group(2)
        items.append({
            'id': m.group(2),
            'name': name,
            'price': _makeshop_price(blk),
            'url': urljoin(base, htmllib.unescape(m.group(1))),
            'soldout': _makeshop_soldout(blk),
        })
    return items


def parse_bbambam(page, base):
    return parse_makeshop(page, base, r'(?=<li class="product_item">)', r'<p class="prdname">(.*?)</p>')


def parse_coupleshot(page, base):
    # name is the first line after the icon images inside span.addviewdesc
    return parse_makeshop(page, base, r'(?=<table cellpadding=0 cellspacing=0 border=0 width=320>)',
                           r"class=addviewdesc[^>]*>(?:\s*<img[^>]*>)*\s*(?:<br\s*/?>)?(.*?)</br>")


def parse_foret(page, base):
    return parse_makeshop(page, base, r'(?=<div class="item item_\d+")', r'<div class="name"[^>]*>\s*<a[^>]*>(.*?)</a>')


# ---------------------------------------------------------------- imweb
def parse_imweb(page, base):
    items, seen = [], set()
    for blk in re.split(r'(?=<div[^>]*class="shop-item _shop_item")', page)[1:]:
        m = re.search(r"data-product-properties='([^']*)'", blk)
        if not m:
            continue
        try:
            d = json.loads(htmllib.unescape(m.group(1)))
        except ValueError:
            continue
        pid = str(d.get('idx'))
        if pid in seen:
            continue
        seen.add(pid)
        link = re.search(r'href="([^"]*\?idx=%s)"' % pid, blk)
        price = d.get('price')
        items.append({
            'id': pid,
            'name': d.get('name', pid),
            'price': '{:,}원'.format(price) if price else '',
            'url': urljoin(base, link.group(1)) if link else base,
            'soldout': bool(re.search(r"class=['\"][^'\"]*\bsold_?out\b", blk, flags=re.I)),
        })
    return items


# ---------------------------------------------------------------- Sixshop (rendered DOM)
def parse_sixshop(page, base):
    items, seen = [], set()
    for blk in re.split(r'(?=<div[^>]*class="shopProductWrapper)', page)[1:]:
        pid = re.search(r'data-productno="(\d+)"', blk)
        link = re.search(r'href="([^"]*/product/[^"]*)"', blk)
        if not pid or pid.group(1) in seen:
            continue
        seen.add(pid.group(1))
        nm = re.search(r'class="shopProduct productName"[^>]*>(.*?)</div>', blk, flags=re.S)
        pr = re.search(r'class="productPriceSpan"[^>]*>(.*?)</span>', blk, flags=re.S)
        price = clean(pr.group(1)) if pr else ''
        items.append({
            'id': pid.group(1),
            'name': clean(nm.group(1)) if nm else pid.group(1),
            'price': '' if price.replace(',', '').strip('0원 ') == '' else price,
            'url': urljoin(base, htmllib.unescape(link.group(1))) if link else base,
            'soldout': 'soldOutBadge' in blk or bool(re.search(r'sold\s*out|품절', clean(price), flags=re.I)),
        })
    return items


# ---------------------------------------------------------------- Shopify (products.json)
def parse_shopify(data, base):
    items = []
    for p in data.get('products', []):
        avail, out = [], []
        for v in p.get('variants', []):
            label = v.get('title') or ''
            if label == 'Default Title':
                label = ''
            (avail if v.get('available') else out).append(label)
        prices = [float(v['price']) for v in p.get('variants', []) if v.get('price')]
        items.append({
            'id': str(p['id']),
            'name': p.get('title', ''),
            'price': ('%s SEK' % ('{:,.0f}'.format(min(prices)))) if prices else '',
            'url': '%s/products/%s' % (base.rstrip('/'), p.get('handle', '')),
            'soldout': not avail,
            'sizes': [x for x in avail if x],
            'sizes_out': [x for x in out if x],
        })
    return items


# ---------------------------------------------------------------- product sizes
def _option_label(text):
    t = clean(text)
    t = re.sub(r'\s*\[?\(?\s*(품절|sold\s*out)\s*\)?\]?\s*', ' ', t, flags=re.I).strip()
    return re.sub(r'\s*\(?[+-]\s*[\d,]+\s*원?\)?$', '', t).strip()


def parse_sizes(page):
    """Return (available, sold_out) option labels from a product detail page, or None if unknown."""
    # Cafe24 keeps per-option stock in a JS variable
    m = re.search(r"option_stock_data\s*=\s*'(.*?)';", page, flags=re.S)
    if m:
        try:
            data = json.loads(m.group(1).replace("\\'", "'").encode().decode('unicode_escape')
                              if '\\u' in m.group(1) else m.group(1).replace('\\"', '"'))
        except ValueError:
            data = None
        if isinstance(data, dict) and data:
            avail, out = [], []
            for opt in data.values():
                label = opt.get('option_value_orginal') or opt.get('option_value') or ''
                if isinstance(label, list):
                    label = '/'.join(str(x) for x in label)
                label = _option_label(str(label))
                if not label or opt.get('is_display') == 'F':
                    continue
                # public pages only carry stock_number for options that ran out
                soldout = opt.get('is_selling', 'T') != 'T' or opt.get('is_auto_soldout') == 'T' or (
                    opt.get('use_stock') and opt.get('use_soldout') == 'T'
                    and opt.get('stock_number') is not None and float(opt['stock_number']) <= 0)
                (out if soldout else avail).append(label)
            if avail or out:
                return avail, out
    # Generic: <select> options (MakeShop leaves them unclosed), sold-out ones say 품절/sold out
    avail, out = [], []
    for sel in re.findall(r'<select[^>]*>(.*?)</select>', page, flags=re.S | re.I):
        for attrs, txt in re.findall(r'<option\b([^>]*)>(.*?)(?=<option\b|</option>|$)', sel, flags=re.S | re.I):
            val = re.search(r'value=["\']?([^"\'\s>]*)', attrs)
            if not val or not val.group(1) or val.group(1) in ('*', '**'):
                continue
            ori = re.search(r'ori_text="([^"]*)"', attrs)
            label = _option_label(ori.group(1) if ori else txt)
            if not label or label.startswith(('-', '[필수]')) or '옵션' in label or '선택' in label \
                    or '★' in label or label.lower() == 'rating':
                continue
            if re.search(r'품절|sold\s*out', txt, flags=re.I) or re.search(r'\bdisabled\b', attrs):
                out.append(label)
            else:
                avail.append(label)
    if avail or out:
        return avail, out
    return None
