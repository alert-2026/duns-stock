import json, datetime, importlib.util
spec = importlib.util.spec_from_file_location('c', 'check_showroom.py'); c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
out = [str(datetime.datetime.now(c.KST))]
q = 'query h($scheduleParams: ScheduleParams) { schedule(input: $scheduleParams) { bizItemSchedule { hourly { unitStartTime unitStock unitBookingCount isUnitSaleDay } } } }'
d = c.gql('h', q, {'scheduleParams': {'businessTypeId': 12, 'businessId': c.BIZ, 'bizItemId': '8129134', 'startDateTime': '2026-10-21T00:00:00', 'endDateTime': '2026-10-25T23:59:59', 'fixedTime': True, 'includesHolidaySchedules': True}})
h = ((d.get('schedule') or {}).get('bizItemSchedule') or {}).get('hourly') or []
free = [x['unitStartTime'][:16] for x in h if x['unitStock'] > x['unitBookingCount'] and x.get('isUnitSaleDay') is not False]
out.append(f'slots {len(h)} free {free}')
out.append('visible ' + str(c.shop_visible()))
open('/tmp/res/probe.txt', 'w').write('\n'.join(out) + '\n' + '\n'.join(c.LOG))
