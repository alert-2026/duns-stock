import sys, re, html
sys.path.insert(0, '.')
import check_stock as cs
for u in ('https://www.foretforet.com/shop/shopbrand.html?xcode=021&mcode=001&scode=090&type=Y','https://www.foretforet.com/'):
    p = html.unescape(cs.fetch(u))
    print('==',u,len(p))
    for m in re.finditer(r'(misha|미샤|퍼프|puff)', p, flags=re.I):
        print(p[max(0,m.start()-250):m.start()+80].replace('\n',' '))
        print('--')
