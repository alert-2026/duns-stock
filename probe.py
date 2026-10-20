import json, urllib.request, urllib.error, datetime
UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148'
def post(op, q, v):
    req = urllib.request.Request(f'https://m.booking.naver.com/graphql?opName={op}', json.dumps({'operationName': op, 'variables': v, 'query': q}).encode(),
        {'User-Agent': UA, 'Content-Type': 'application/json', 'Referer': 'https://m.booking.naver.com/booking/12/bizes/1638569'})
    try:
        with urllib.request.urlopen(req, timeout=20) as r: return r.status, r.read().decode()[:2500]
    except urllib.error.HTTPError as e: return e.code, e.read().decode()[:2500]
B='1638569'
out=[str(datetime.datetime.utcnow())]
out.append(post('bizItems','query bizItems($input: BizItemsParams) { bizItems(input: $input) { bizItemId name isImp isClosedBooking bookableSettingJson } }',{'input':{'businessId':B,'lang':'ko','projections':'RESOURCE'}}))
out.append(post('business','query business($input: BusinessParams) { business(input: $input) { businessId name isImp } }',{'input':{'businessId':B,'lang':'ko','projections':'RESOURCE'}}))
out.append(post('h','query h($scheduleParams: ScheduleParams) { schedule(input: $scheduleParams) { bizItemSchedule { hourly { unitStartTime unitStock unitBookingCount } } } }',{'scheduleParams':{'businessTypeId':12,'businessId':B,'bizItemId':'8129134','startDateTime':'2026-10-21T00:00:00','endDateTime':'2026-10-21T23:59:59','fixedTime':True,'includesHolidaySchedules':True}}))
for u in ['https://m.booking.naver.com/booking/12/bizes/1638569/items/8129134','https://booking.naver.com/booking/12/bizes/1638569']:
    try:
        r=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':UA}),timeout=20); out.append((u,r.status,r.geturl()))
    except Exception as e: out.append((u,str(e)))
open('/tmp/res/probe.txt','w').write('\n\n'.join(map(str,out)))
