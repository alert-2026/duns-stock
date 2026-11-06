import urllib.error, json, os, re, urllib.request, sys
from concurrent.futures import ThreadPoolExecutor
R=os.environ['REPO']; T=os.environ['GH_TOKEN']
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k): return None
opener=urllib.request.build_opener(NoRedirect)
def logs(path):
    req=urllib.request.Request('https://api.github.com'+path, headers={'Authorization':'Bearer '+T})
    try:
        r=opener.open(req, timeout=60); return r.read().decode('utf-8','replace')
    except urllib.error.HTTPError as e:
        if e.code in (301,302,303,307):
            with urllib.request.urlopen(e.headers['Location'], timeout=120) as r2:
                return r2.read().decode('utf-8','replace')
        raise
def api(path, raw=False):
    req=urllib.request.Request('https://api.github.com'+path, headers={'Authorization':'Bearer '+T,'Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(req, timeout=60) as r:
        b=r.read()
    return b.decode('utf-8','replace') if raw else json.loads(b)
for j in api('/repos/%s/actions/runs/42163291861/jobs'%R)['jobs']:
    if 'cc' not in j['name']: continue
    t=logs('/repos/%s/actions/jobs/%d/logs'%(R,j['id']))
    for l in t.split('\n'):
        if re.search(r'(재입고|신상|already|SKIP|stopped|rror|coupleshot:\d+/)',l): print(l[29:200])
