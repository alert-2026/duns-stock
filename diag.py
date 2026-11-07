import sys, re
sys.path.insert(0, '.')
import check_stock as cs
p = cs.fetch('https://www.foretforet.com/shop/shopbrand.html?xcode=021&mcode=001&scode=090&type=Y')
for m in re.finditer(r'<a[^>]*href="([^"]*shopbrand[^"]*)"[^>]*>(.*?)</a>', p, flags=re.S|re.I):
    t = re.sub(r'<[^>]+>', '', m.group(2)).strip()
    if re.search(r'misha|미샤|puff|퍼프|duns|던스', m.group(1)+t, flags=re.I): print(m.group(1), '|', t[:60])
print('---all brand links (021)')
seen=set()
for m in re.finditer(r'href="([^"]*xcode=021[^"]*)"[^>]*>(.*?)</a>', p, flags=re.S|re.I):
    t = re.sub(r'<[^>]+>', '', m.group(2)).strip()
    if m.group(1) in seen: continue
    seen.add(m.group(1)); print(m.group(1), '|', t[:50])
