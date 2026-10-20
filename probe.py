import json, datetime, importlib.util
spec = importlib.util.spec_from_file_location('c', 'check_showroom.py'); c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
out = [str(datetime.datetime.now(c.KST))]
out.append(json.dumps(c.gql('business', 'query business($input: BusinessParams) { business(input: $input) { businessId name } }', {'input': {'businessId': c.BIZ, 'lang': 'ko', 'projections': 'RESOURCE'}}), ensure_ascii=False))
out.append(json.dumps(c.gql('bizItems', 'query bizItems($input: BizItemsParams) { bizItems(input: $input) { bizItemId name isImp isClosedBooking isClosedBookingUser bookingAvailableCode bookableSettingJson } }', {'input': {'businessId': c.BIZ, 'lang': 'ko', 'projections': 'RESOURCE'}}), ensure_ascii=False))
d = c.gql('h', 'query h($scheduleParams: ScheduleParams) { schedule(input: $scheduleParams) { bizItemSchedule { hourly { unitStartTime unitStock unitBookingCount } } } }', {'scheduleParams': {'businessTypeId': 12, 'businessId': c.BIZ, 'bizItemId': '8129134', 'startDateTime': '2026-10-21T00:00:00', 'endDateTime': '2026-10-25T23:59:59', 'fixedTime': True, 'includesHolidaySchedules': True}})
h = ((d.get('schedule') or {}).get('bizItemSchedule') or {}).get('hourly') or []
out.append(f"slots {len(h)} booked {sum(1 for x in h if x['unitBookingCount'])} free {[x['unitStartTime'] for x in h if x['unitStock'] > x['unitBookingCount']]}")
open('/tmp/res/probe.txt', 'w').write('\n'.join(out) + '\n' + '\n'.join(c.LOG))
