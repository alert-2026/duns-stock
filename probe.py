import json, urllib.request, urllib.error
UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148'
def post(op, q, v):
    req = urllib.request.Request(f'https://m.booking.naver.com/graphql?opName={op}', json.dumps({'operationName': op, 'variables': v, 'query': q}).encode(),
        {'User-Agent': UA, 'Content-Type': 'application/json', 'Referer': 'https://m.booking.naver.com/booking/12/bizes/1638569'})
    try:
        with urllib.request.urlopen(req, timeout=20) as r: return r.status, r.read().decode()
    except urllib.error.HTTPError as e: return e.code, e.read().decode()[:3000]
B = '1638569'
fields = 'bizItemId name desc price stock minBookingCount maxBookingCount bookingConfirmCode isOnsitePayment paymentSettingJson extraFeeSettingJson customFormJson optionCategoryMappings bookingCountSettingJson bookableSettingJson priceByDates isRequestMessageUsed bizItemType bizItemSubType'
out = [post('bizItems', 'query bizItems($input: BizItemsParams) { bizItems(input: $input) { ' + fields + ' } }', {'input': {'businessId': B, 'lang': 'ko', 'projections': 'RESOURCE'}})]
# drop fields one by one if a field is rejected
if out[0][0] != 200 or '"errors"' in out[0][1]:
    for f in fields.split():
        out.append((f, post('bizItems', 'query bizItems($input: BizItemsParams) { bizItems(input: $input) { bizItemId ' + f + ' } }', {'input': {'businessId': B, 'lang': 'ko', 'projections': 'RESOURCE'}})))
open('/tmp/res/probe.txt', 'w').write('\n\n'.join(map(str, out)))
