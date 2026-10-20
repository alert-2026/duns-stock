import json, datetime, importlib.util
spec = importlib.util.spec_from_file_location('c', 'check_showroom.py'); c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
out = [str(datetime.datetime.now(c.KST))]
q = 'query h($scheduleParams: ScheduleParams) { schedule(input: $scheduleParams) { bizItemSchedule { hourly { unitStartTime unitStock unitBookingCount bookingCount occupiedBookingCount stock isSaleDay isUnitSaleDay isUnitBusinessDay isBusinessDay saleStartDateTime saleEndDateTime } } } }'
d = c.gql('h', q, {'scheduleParams': {'businessTypeId': 12, 'businessId': c.BIZ, 'bizItemId': '8129134', 'startDateTime': '2026-10-21T00:00:00', 'endDateTime': '2026-10-25T23:59:59', 'fixedTime': True, 'includesHolidaySchedules': True}})
h = ((d.get('schedule') or {}).get('bizItemSchedule') or {}).get('hourly') or []
for x in h:
    if x['unitStartTime'][:16] in ('2026-10-22 16:45', '2026-10-25 14:30', '2026-10-22 16:30', '2026-10-25 14:15'):
        out.append(json.dumps(x, ensure_ascii=False))
out.append(json.dumps(c.gql('business', 'query business($input: BusinessParams) { business(input: $input) { businessId } }', {'input': {'businessId': c.BIZ, 'lang': 'ko', 'projections': 'RESOURCE'}})))
open('/tmp/res/probe.txt', 'w').write('\n'.join(out) + '\n' + '\n'.join(c.LOG))
