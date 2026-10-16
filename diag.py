import time, check_stock as c
from concurrent.futures import ThreadPoolExecutor
def timed(s):
    t = time.time(); k, items, err = c.check_shop(s); return k, len(items or []), err, time.time() - t
t = time.time()
with ThreadPoolExecutor(8) as ex:
    for k, n, err, d in ex.map(timed, c.SHOPS):
        print('%-16s %5d %6.1fs %s' % (k, n, d, err or ''))
print('total %.1fs' % (time.time() - t))
t = time.time()
with ThreadPoolExecutor(8) as ex:
    res = list(ex.map(timed, c.SHOPS))
print('second pass %.1fs' % (time.time() - t))
