import json, datetime, importlib.util, subprocess
spec = importlib.util.spec_from_file_location('c', 'check_desi.py'); c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
now = datetime.datetime.now(c.KST)
out = [str(now), 'free ' + json.dumps(c.free_days('8170337', now))]
q = 'query schedule($scheduleParams: ScheduleParams) { schedule(input: $scheduleParams) { bizItemSchedule { daily { date } } } }'
d = c.gql('schedule', q, {'scheduleParams': {'businessTypeId': 5, 'businessId': c.BIZ, 'bizItemId': '8170337', 'startDateTime': now.strftime('%Y-%m-%dT00:00:00'), 'endDateTime': (now + datetime.timedelta(days=60)).strftime('%Y-%m-%dT23:59:59'), 'fixedTime': True, 'includesHolidaySchedules': True}})
days = d['schedule']['bizItemSchedule']['daily']['date']
for k, v in sorted(days.items()):
    out.append(f"{k} sale={v['isSaleDay']} biz={v['isBusinessDay']} stock={v['stock']} booked={v['bookingCount']} occ={v['occupiedBookingCount']}")
for ext in ['', '/items/8170337']:
    r = subprocess.run(['curl', '-sSL', '-A', c.UA, '-w', '\n%{http_code} %{url_effective}', c.PAGE + ext], capture_output=True, text=True).stdout
    out.append('page' + ext + ' ' + r.splitlines()[-1] + ' len ' + str(len(r)) + ' has item ' + str('던스11월' in r))
    out.append('  isImp ' + str(__import__('re').findall(r'"(?:isImp|isClosedBooking|bookingAvailableCode)":[^,]{0,20}', r)[:8]))
open('/tmp/res/probe.txt', 'w').write('\n'.join(out) + '\n' + '\n'.join(c.LOG))
