import json, importlib.util, urllib.request
spec = importlib.util.spec_from_file_location('c', 'check_desi.py'); c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
out = []
q = 'query bizItems($input: BizItemsParams) { bizItems(input: $input) { bizItemId name } }'
body = {'operationName': 'bizItems', 'variables': {'input': {'businessId': c.BIZ, 'lang': 'ko', 'projections': 'RESOURCE'}}, 'query': q}
for ref in [c.PAGE, c.PAGE + '/items/8170337', 'https://m.booking.naver.com/booking/12/bizes/1638569', '']:
    try:
        out.append(ref + ' -> ' + json.dumps(c.post('https://m.booking.naver.com/graphql?opName=bizItems', body, referer=ref), ensure_ascii=False)[:300])
    except Exception as e:
        out.append(ref + ' FAIL ' + repr(e))
open('/tmp/res/probe.txt', 'w').write('\n'.join(out) + '\n' + '\n'.join(c.LOG))
