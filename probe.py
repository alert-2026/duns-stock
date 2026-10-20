import json, urllib.request, urllib.error, datetime, importlib.util
spec = importlib.util.spec_from_file_location('c', 'check_showroom.py'); c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
now = datetime.datetime.now(c.KST)
q = 'query h($scheduleParams: ScheduleParams) { schedule(input: $scheduleParams) { bizItemSchedule { hourly { unitStartTime unitStock unitBookingCount } } } }'
d = c.gql('h', q, {'scheduleParams': {'businessTypeId': 12, 'businessId': c.BIZ, 'bizItemId': '8129134', 'startDateTime': '2026-10-21T00:00:00', 'endDateTime': '2026-10-25T23:59:59', 'fixedTime': True, 'includesHolidaySchedules': True}})
h = d['schedule']['bizItemSchedule']['hourly']
free = [x['unitStartTime'][:16] for x in h if x['unitStock'] > x['unitBookingCount']]
open('/tmp/res/probe.txt', 'w').write(f"{now} total {len(h)} booked {sum(1 for x in h if x['unitBookingCount'])} free {len(free)}\n" + c.by_day(free) + '\nvisible ' + str(c.shop_visible()))
