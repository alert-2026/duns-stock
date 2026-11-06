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

seen=set()
for wf in ('quick.yml','check.yml','fast.yml'):
    runs=api('/repos/%s/actions/workflows/%s/runs?per_page=40&created=>=2026-11-05T15:00:00Z'%(R,wf))['workflow_runs']
    for run in sorted(runs,key=lambda r:r['created_at']):
        if run['status']!='completed': continue
        for j in api('/repos/%s/actions/runs/%d/jobs'%(R,run['id']))['jobs']:
            if wf=='quick.yml' and 'cc' not in j['name']: continue
            try: t=logs('/repos/%s/actions/jobs/%d/logs'%(R,j['id']))
            except Exception as e: print('ERR',wf,j['id'],e); continue
            print('==',wf,run['run_number'],j['name'],j['started_at'],j['completed_at'])
            for l in t.split('\n'):
                if '미니커플샷' in l or re.search(r'coupleshot:\d+/',l) or 'coupleshot' in l and ('rror' in l or 'fail' in l): print(l[29:200])
