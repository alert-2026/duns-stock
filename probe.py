import json, os, subprocess, datetime
os.environ['SHOWROOM_STATE'] = '/tmp/st.json'
# 1) real run, 2) pretend booking is open and one time was taken before, to see the alert text
r1 = subprocess.run(['python3', 'check_showroom.py'], capture_output=True, text=True).stdout
import importlib.util
spec = importlib.util.spec_from_file_location('c', 'check_showroom.py'); c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
now = datetime.datetime(2026, 10, 20, 11, 5, tzinfo=c.KST)
slots = c.free_slots('8129134', now)
open('/tmp/res/probe.txt', 'w').write(r1 + '\n\nfree after open: ' + str(len(slots or [])) + '\n' + c.by_day(slots or [], 12) + '\n\nfreed example:\n' + c.by_day((slots or [])[3:5]))
