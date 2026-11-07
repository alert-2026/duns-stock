import sys, collections
sys.path.insert(0, '.')
import check_stock as cs
for u in ('https://www.foretforet.com/shop/shopbrand.html?xcode=021&mcode=001&scode=232&type=Y','https://www.foretforet.com/shop/shopbrand.html?xcode=021&mcode=001&scode=090&type=Y'):
    its = cs.foret_items(u)
    print(u[-20:], len(its), collections.Counter(i['soldout'] for i in its))
    for i in its[:8]: print(' ', i['soldout'], i['name'][:60], i['price'], i['url'][:90])
