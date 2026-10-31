import json, datetime, importlib.util, re, subprocess
spec = importlib.util.spec_from_file_location('c', 'check_showroom.py'); c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
c.BIZ = '1617276'
out = []
html = subprocess.run(['curl', '-sSL', '-A', c.UA, 'https://m.booking.naver.com/booking/5/bizes/1617276/items/8170337'], capture_output=True, text=True).stdout
js = ''
main = re.search(r'/mobile/static/js/main\.[a-z0-9]+\.js', html).group(0)
js = subprocess.run(['curl', '-sSL', 'https://m.booking.naver.com' + main], capture_output=True, text=True).stdout
# lazy chunks are listed in main.js; fetch those whose names hint at schedules/calendars
names = sorted(set(re.findall(r'"([A-Za-z0-9_\-]*(?:[Ss]chedule|[Cc]alendar|Daily|daily)[A-Za-z0-9_\-]*)"\s*:\s*"([0-9a-f]{8})"', js)))
out.append('chunks ' + str(names[:40]))
for n, h in names[:40]:
    js += subprocess.run(['curl', '-sSL', f'https://m.booking.naver.com/mobile/static/js/{n}.{h}.chunk.js'], capture_output=True, text=True).stdout
for m in sorted(set(re.findall(r'(?:query|fragment) [A-Za-z]*(?:[Ss]chedule|[Dd]aily)[^`"]{0,700}', js)))[:30]:
    out.append('Q ' + m)
open('/tmp/res/probe.txt', 'w').write('\n'.join(out) + '\n' + '\n'.join(c.LOG))
