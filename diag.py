import sys, os, re, json
sys.path.insert(0, '.')
import check_stock as cs, parsers
os.makedirs('pages', exist_ok=True)
u='http://www.coupleshot.com/shop/shopdetail.html?branduid=575496&xcode=054&mcode=015&scode=&type=X&search=&sort=order'
p=cs.fetch(u)
open('pages/575496.html','w').write(p)
print('len',len(p))
print('parse_sizes',parsers.parse_sizes(p))
for m in re.finditer(r'<select[^>]*>.*?</select>', p, flags=re.S|re.I):
    print('SELECT', m.group(0)[:3000])
for kw in ('soldout','품절','sold_out','stock','optionStock','opt_stock','basket'):
    for m in list(re.finditer(kw, p, flags=re.I))[:6]:
        print(kw, '::', p[max(0,m.start()-200):m.start()+200].replace('\n',' '))
# list pages: find this item
L='http://www.coupleshot.com/shop/shopbrand.html?xcode=054&type=X'
for n in range(1,25):
    lp=cs.fetch(L+'&page=%d'%n)
    for it in parsers.parse_coupleshot(lp, L):
        if it['id']=='575496':
            print('LIST page',n,it)
            i=lp.find('575496'); open('pages/list575496.html','w').write(lp[max(0,i-3000):i+3000])
