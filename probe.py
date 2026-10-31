import subprocess
r1 = subprocess.run(['python3', 'check_desi.py'], capture_output=True, text=True)
r2 = subprocess.run(['python3', 'check_desi.py'], capture_output=True, text=True)
open('/tmp/res/probe.txt', 'w').write('RUN1\n' + r1.stdout + r1.stderr + 'RUN2\n' + r2.stdout + r2.stderr + open('desi-state.json').read()[:1500])
