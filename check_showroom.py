"""Watches the Duns showroom Naver booking page and sends a Telegram alert when booking opens
or a time slot has room. Run by .github/workflows/showroom.yml; state is kept in showroom-state.json."""
import datetime, json, os, re, subprocess, sys, urllib.request

BIZ = '1638569'
PAGE = f'https://m.booking.naver.com/booking/12/bizes/{BIZ}'
UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148'
STATE = os.environ.get('SHOWROOM_STATE', 'showroom-state.json')
KST = datetime.timezone(datetime.timedelta(hours=9))
LOG = []


def log(*a):
    line = ' '.join(str(x) for x in a)
    LOG.append(line)
    print(line, flush=True)


def http(url, body=None):
    headers = {'User-Agent': UA, 'Referer': PAGE, 'Accept': 'application/json, text/html'}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status, r.read().decode('utf-8', 'replace')


def gql(op, query, variables):
    st, text = http(f'https://m.booking.naver.com/graphql?opName={op}',
                    {'operationName': op, 'variables': variables, 'query': query})
    j = json.loads(text)
    if j.get('errors'):
        log('graphql', op, 'errors', json.dumps(j['errors'], ensure_ascii=False)[:500])
    return j.get('data') or {}


def biz_items():
    q = ('query bizItems($input: BizItemsParams) { bizItems(input: $input) '
         '{ id bizItemId name bookableStatus isImp startDate endDate bookingTimeUnitCode } }')
    d = gql('bizItems', q, {'input': {'businessId': BIZ, 'lang': 'ko', 'projections': 'RESOURCE'}})
    return d.get('bizItems') or []


def open_slots(item_id, days=60):
    now = datetime.datetime.now(KST)
    end = now + datetime.timedelta(days=days)
    q = ('query schedule($scheduleParams: ScheduleParams) { schedule(input: $scheduleParams) '
         '{ bizItemSchedule { hourly { unitStartTime unitStock unitBookingCount isUnitSaleDay isUnitBusinessDay } '
         'daily { date stock bookingCount isSaleDay isBusinessDay } } } }')
    d = gql('schedule', q, {'scheduleParams': {
        'businessTypeId': 12, 'businessId': BIZ, 'bizItemId': str(item_id),
        'startDateTime': now.strftime('%Y-%m-%dT00:00:00'), 'endDateTime': end.strftime('%Y-%m-%dT23:59:59'),
        'fixedTime': True, 'includesHolidaySchedules': True}})
    sched = ((d.get('schedule') or {}).get('bizItemSchedule') or {})
    slots = set()
    for h in sched.get('hourly') or []:
        left = (h.get('unitStock') or 0) - (h.get('unitBookingCount') or 0)
        if left > 0 and h.get('isUnitSaleDay') is not False and h.get('isUnitBusinessDay') is not False:
            slots.add(h['unitStartTime'][:16])
    if not slots:
        for day in sched.get('daily') or []:
            left = (day.get('stock') or 0) - (day.get('bookingCount') or 0)
            if left > 0 and day.get('isSaleDay') is not False and day.get('isBusinessDay') is not False:
                slots.add(day['date'][:10])
    return slots


def telegram(text):
    token = os.environ.get('TELEGRAM_TOKEN', '').strip()
    chat = os.environ.get('TELEGRAM_CHAT_ID', '').strip()
    if not token or not chat:
        log('no telegram secrets; would send:', text)
        return
    http(f'https://api.telegram.org/bot{token}/sendMessage',
         {'chat_id': chat, 'text': text, 'disable_web_page_preview': True})


def pretty(slot):
    try:
        t = datetime.datetime.fromisoformat(slot)
        wd = '월화수목금토일'[t.weekday()]
        return t.strftime(f'%m/%d({wd}) %H:%M') if len(slot) > 10 else t.strftime(f'%m/%d({wd})')
    except ValueError:
        return slot


def main():
    try:
        state = json.load(open(STATE))
    except (OSError, ValueError):
        state = {}
    first = not state
    items = biz_items()
    log('bizItems', json.dumps(items, ensure_ascii=False)[:800])
    bookable = [i for i in items if i.get('isImp') is not False]
    now_slots = {}
    for it in bookable:
        iid = it.get('bizItemId') or it.get('id')
        now_slots[str(iid)] = sorted(open_slots(iid))
        log('item', iid, it.get('name'), 'open slots', len(now_slots[str(iid)]), now_slots[str(iid)][:10])
    msgs = []
    if bookable and not state.get('open') and not first:
        msgs.append('예약 페이지가 열렸어요: ' + ', '.join(i.get('name') or '' for i in bookable))
    for it in bookable:
        iid = str(it.get('bizItemId') or it.get('id'))
        new = [s for s in now_slots[iid] if s not in set(state.get('slots', {}).get(iid, []))]
        if new and not first:
            msgs.append(f"[{it.get('name')}] 빈자리 {len(new)}개\n" + '\n'.join('· ' + pretty(s) for s in new[:15])
                        + ('\n…' if len(new) > 15 else ''))
    if msgs:
        stamp = datetime.datetime.now(KST).strftime('%m/%d %H:%M')
        telegram(f'🔔 [쇼룸 예약] 던스스웨덴 ({stamp}, KST)\n\n' + '\n\n'.join(msgs) + f'\n\n{PAGE}')
        log('alert sent', len(msgs))
    json.dump({'open': bool(bookable), 'slots': now_slots}, open(STATE, 'w'), ensure_ascii=False)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:  # keep the loop going; the log shows what broke
        log('error', type(e).__name__, e)
    with open('showroom-log.txt', 'a') as f:
        f.write(datetime.datetime.now(KST).isoformat(timespec='seconds') + '\n' + '\n'.join(LOG) + '\n')
