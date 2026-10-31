import json, re, subprocess
out = []
UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148'
def curl(url, name):
    r = subprocess.run(['curl', '-sSL', '-A', UA, '-o', f'/tmp/res/{name}', '-w', '%{http_code} %{url_effective}', url], capture_output=True, text=True)
    out.append(f'{name}: {r.stdout} {r.stderr[:200]}')
    try:
        return r.stdout.split(' ', 1)[1], open(f'/tmp/res/{name}', errors='replace').read()
    except Exception:
        return '', ''
final, html = curl('https://naver.me/xhPT0QGG', 'naverme.html')
ids = set(re.findall(r'place/(\d+)', final + html)) | set(re.findall(r'pinId=(\d+)', final)) | set(re.findall(r'"id":"(\d{6,})"', html)[:3])
out.append('place ids ' + str(ids))
for pid in list(ids)[:3]:
    for tab in ['home', 'booking', 'ticket']:
        _, h = curl(f'https://m.place.naver.com/place/{pid}/{tab}', f'place-{pid}-{tab}.html')
        out.append(f'{pid} {tab} bizes: ' + str(sorted(set(re.findall(r'booking/(\d+)/bizes/(\d+)', h)))))
        out.append(f'{pid} {tab} bookingBusinessId: ' + str(sorted(set(re.findall(r'"bookingBusinessId":"?(\d+)', h)))))
for h in [open(f) .read() for f in __import__('glob').glob('/tmp/res/place-*')]:
    out.append('booking urls: ' + str(sorted(set(re.findall(r'https?://[a-z.]*booking\.naver\.com[^"\\ ]{0,120}', h)))[:20]))
open('/tmp/res/probe.txt', 'w').write('\n'.join(out) + '\n')
