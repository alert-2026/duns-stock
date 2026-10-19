import json, re, urllib.request, urllib.error
UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148'
def post(op, q, v):
    req = urllib.request.Request(f'https://m.booking.naver.com/graphql?opName={op}', json.dumps({'operationName': op, 'variables': v, 'query': q}).encode(),
        {'User-Agent': UA, 'Content-Type': 'application/json', 'Referer': 'https://m.booking.naver.com/booking/12/bizes/1638569'})
    try:
        with urllib.request.urlopen(req, timeout=20) as r: return r.status, r.read().decode()[:1500]
    except urllib.error.HTTPError as e: return e.code, e.read().decode()[:1500]
out = []
B = '1638569'
out.append(post('bizItems', 'query bizItems($input: BizItemsParams) { bizItems(input: $input) { bizItemId name isImp } }', {'input': {'businessId': B, 'lang': 'ko', 'projections': 'RESOURCE'}}))
out.append(post('business', 'query business($input: BusinessParams) { business(input: $input) { businessId name } }', {'input': {'businessId': B, 'lang': 'ko', 'projections': 'RESOURCE'}}))
out.append(post('hourlySchedule', 'query hourlySchedule($scheduleParams: ScheduleParams) { schedule(input: $scheduleParams) { bizItemSchedule { hourly { unitStartTime unitStock unitBookingCount isUnitSaleDay } } } }',
    {'scheduleParams': {'businessTypeId': 12, 'businessId': B, 'bizItemId': '1', 'startDateTime': '2026-10-19T00:00:00', 'endDateTime': '2026-10-31T23:59:59', 'fixedTime': True, 'includesHolidaySchedules': True}}))
s = open('/tmp/main.js', errors='replace').read()
ctx = sorted(set(m.group(0) for m in re.finditer(r'.{0,250}(startDateTime|includesHolidaySchedules).{0,250}', s)))[:12]
ctx2 = sorted(set(m.group(0) for m in re.finditer(r'fragment BizItemFragment[\s\S]{0,1500}', s)))[:1]
open('/tmp/res/probe.txt', 'w').write('\n\n'.join(map(str, out)) + '\n\n=== ctx\n' + '\n---\n'.join(ctx) + '\n\n=== frag\n' + '\n'.join(ctx2))
