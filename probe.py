import json, urllib.request, urllib.error
UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148'
def post(op, q, v):
    req = urllib.request.Request(f'https://m.booking.naver.com/graphql?opName={op}', json.dumps({'operationName': op, 'variables': v, 'query': q}).encode(),
        {'User-Agent': UA, 'Content-Type': 'application/json', 'Referer': 'https://m.booking.naver.com/booking/12/bizes/1638569'})
    try:
        with urllib.request.urlopen(req, timeout=20) as r: return r.status, r.read().decode()[:3000]
    except urllib.error.HTTPError as e: return e.code, e.read().decode()[:3000]
B, I = '1638569', '8129134'
out = [post('bizItems', 'query bizItems($input: BizItemsParams) { bizItems(input: $input) { bizItemId name isImp rawIsImp startDate endDate availableStartDate bookingAvailableCode bookingAvailableValue isClosedBooking isClosedBookingUser bookableSettingJson bookingTimeUnitCode isPeriodFixed stock inspectionStatusCode } }', {'input': {'businessId': B, 'lang': 'ko', 'projections': 'RESOURCE'}})]
H = 'query hourlySchedule($scheduleParams: ScheduleParams) { schedule(input: $scheduleParams) { bizItemSchedule { hourly { unitStartTime unitStock unitBookingCount stock bookingCount isUnitSaleDay isUnitBusinessDay isSaleDay saleStartDateTime } } } }'
D = 'query daily($scheduleParams: ScheduleParams) { schedule(input: $scheduleParams) { bizItemSchedule { daily { date } } } }'
for p in [{'businessTypeId': 12, 'businessId': B, 'bizItemId': I, 'startDateTime': '2026-10-19T00:00:00', 'endDateTime': '2026-12-31T23:59:59', 'fixedTime': True, 'includesHolidaySchedules': True},
          {'businessTypeId': 12, 'businessId': B, 'bizItemId': I, 'startDateTime': '2026-10-19T00:00:00', 'endDateTime': '2026-12-31T23:59:59'}]:
    out.append(post('hourlySchedule', H, {'scheduleParams': p}))
    out.append(post('daily', D, {'scheduleParams': p}))
open('/tmp/res/probe.txt', 'w').write('\n\n'.join(map(str, out)))
