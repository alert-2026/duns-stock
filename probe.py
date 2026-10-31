import json, datetime, importlib.util
spec = importlib.util.spec_from_file_location('c', 'check_showroom.py'); c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
c.BIZ = '1617276'
out = []
now = datetime.datetime.now(c.KST)
def sched(fields, fixed=True, days=70):
    q = 'query schedule($scheduleParams: ScheduleParams) { schedule(input: $scheduleParams) { bizItemSchedule { ' + fields + ' } } }'
    try:
        d = c.gql('schedule', q, {'scheduleParams': {'businessTypeId': 5, 'businessId': c.BIZ, 'bizItemId': '8170337', 'startDateTime': now.strftime('%Y-%m-%dT00:00:00'), 'endDateTime': (now + datetime.timedelta(days=days)).strftime('%Y-%m-%dT23:59:59'), 'fixedTime': fixed, 'includesHolidaySchedules': True}})
        out.append(fields[:60] + f' fixed={fixed}: ' + json.dumps(d, ensure_ascii=False)[:2500])
    except Exception as e:
        out.append(fields[:60] + ' FAIL ' + repr(e) + ' ' + (e.read().decode()[:400] if hasattr(e, 'read') else ''))
sched('daily { date }')
for f in ['stock', 'bookingCount', 'isSaleDay', 'isBusinessDay', 'occupiedBookingCount', 'isHoliday', 'minBookingCount', 'maxBookingCount', 'saleStartDateTime', 'saleEndDateTime']:
    sched('daily { date ' + f + ' }')
sched('hourly { unitStartTime unitStock unitBookingCount stock bookingCount isSaleDay isUnitSaleDay }', fixed=False)
open('/tmp/res/probe.txt', 'w').write('\n'.join(out) + '\n' + '\n'.join(c.LOG))
