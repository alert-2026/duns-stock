import json, datetime, importlib.util, re, subprocess
spec = importlib.util.spec_from_file_location('c', 'check_showroom.py'); c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
c.BIZ = '1617276'; c.PAGE = 'https://m.booking.naver.com/booking/5/bizes/1617276'
out = [str(datetime.datetime.now(c.KST))]
r = subprocess.run(['curl', '-sSL', '-A', c.UA, c.PAGE + '/items/8170337'], capture_output=True, text=True)
open('/tmp/res/item.html', 'w').write(r.stdout)
pass # + json.dumps(c.gql('business', 'query business($input: BusinessParams) { business(input: $input) { businessId name businessTypeId serviceName } }', {'input': {'businessId': c.BIZ, 'lang': 'ko', 'projections': 'RESOURCE'}}), ensure_ascii=False))
items = c.gql('bizItems', 'query bizItems($input: BizItemsParams) { bizItems(input: $input) { bizItemId name isImp isClosedBooking bookableSettingJson } }', {'input': {'businessId': c.BIZ, 'lang': 'ko', 'projections': 'RESOURCE'}})
out.append('items ' + json.dumps(items, ensure_ascii=False)[:6000])
now = datetime.datetime.now(c.KST)
for it in (items.get('bizItems') or [])[:12]:
    iid = str(it['bizItemId'])
    for fixed in [True]:
        q = 'query h($scheduleParams: ScheduleParams) { schedule(input: $scheduleParams) { bizItemSchedule { hourly { unitStartTime unitStock unitBookingCount isUnitSaleDay isUnitBusinessDay } } } }'
        d = c.gql('h', q, {'scheduleParams': {'businessTypeId': 5, 'businessId': c.BIZ, 'bizItemId': iid, 'startDateTime': now.strftime('%Y-%m-%dT00:00:00'), 'endDateTime': (now + datetime.timedelta(days=60)).strftime('%Y-%m-%dT23:59:59'), 'fixedTime': fixed, 'includesHolidaySchedules': True}})
        s = (d.get('schedule') or {}).get('bizItemSchedule') or {}
        h = s.get('hourly') or []
        free = [x['unitStartTime'][:16] for x in h if (x.get('unitStock') or 0) > (x.get('unitBookingCount') or 0) and x.get('isUnitSaleDay') is not False]
        out.append(f'{iid} {it.get("name")} fixed={fixed} hourly {len(h)} booked {sum(x.get("unitBookingCount") or 0 for x in h)} free {len(free)} {free[:30]}')
        out.append('  sample ' + json.dumps(h[:3], ensure_ascii=False) )
open('/tmp/res/probe.txt', 'w').write('\n'.join(out) + '\n' + '\n'.join(c.LOG))
