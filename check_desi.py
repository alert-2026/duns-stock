"""Watches 데시디자인's Naver booking page (Duns reform bookings, samee asked on 10/31) and sends a Telegram alert
when a full day frees up (a cancellation), a new booking item appears, or an item opens.
Run by .github/workflows/desi.yml; state in desi-state.json. Booking is per day (no times), read via the daily schedule."""
import datetime, json, os, sys, urllib.request

BIZ = '1617276'
PAGE = f'https://m.booking.naver.com/booking/5/bizes/{BIZ}'
ITEM_PAGE = PAGE + '/items/{item}'
UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148'
STATE = os.environ.get('DESI_STATE', 'desi-state.json')
KST = datetime.timezone(datetime.timedelta(hours=9))
LOG = []


def log(*a):
    line = ' '.join(str(x) for x in a)
    LOG.append(line)
    print(line, flush=True)


def post(url, body, referer=PAGE):
    req = urllib.request.Request(url, json.dumps(body).encode(), {
        'User-Agent': UA, 'Referer': referer, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def gql(op, query, variables):
    j = post(f'https://m.booking.naver.com/graphql?opName={op}',
             {'operationName': op, 'variables': variables, 'query': query})
    if j.get('errors'):
        log('graphql', op, 'errors', json.dumps(j['errors'], ensure_ascii=False)[:300])
    return j.get('data') or {}


def biz_items():
    q = ('query bizItems($input: BizItemsParams) { bizItems(input: $input) '
         '{ bizItemId name isImp isClosedBooking bookableSettingJson } }')
    return gql('bizItems', q, {'input': {'businessId': BIZ, 'lang': 'ko', 'projections': 'RESOURCE'}}).get('bizItems') or []


def is_open(item, now):
    s = item.get('bookableSettingJson') or {}
    if item.get('isImp') is False or item.get('isClosedBooking') or s.get('isPaused'):
        return False
    if s.get('isUseOpen') and not s.get('isOpened'):
        try:
            return now >= datetime.datetime.fromisoformat(s['openDateTime'])
        except (KeyError, ValueError):
            return False
    return True


def free_days(item_id, now):
    """{'2026-11-01': free count} for days on sale. `daily { date }` returns every day's whole record
    (stock, bookingCount, isSaleDay); asking for those fields by name is rejected."""
    q = 'query schedule($scheduleParams: ScheduleParams) { schedule(input: $scheduleParams) { bizItemSchedule { daily { date } } } }'
    d = gql('schedule', q, {'scheduleParams': {
        'businessTypeId': 5, 'businessId': BIZ, 'bizItemId': str(item_id),
        'startDateTime': now.strftime('%Y-%m-%dT00:00:00'),
        'endDateTime': (now + datetime.timedelta(days=90)).strftime('%Y-%m-%dT23:59:59'),
        'fixedTime': True, 'includesHolidaySchedules': True}})
    days = ((((d.get('schedule') or {}).get('bizItemSchedule') or {}).get('daily') or {}).get('date'))
    if not isinstance(days, dict):
        return None
    today = now.strftime('%Y-%m-%d')
    return {k: (v.get('stock') or 0) - (v.get('bookingCount') or 0) for k, v in days.items()
            if k >= today and v.get('isSaleDay') and v.get('isBusinessDay') is not False
            and (v.get('stock') or 0) > (v.get('bookingCount') or 0)}


def telegram(text):
    token = os.environ.get('TELEGRAM_TOKEN', '').strip()
    # same as check_stock.py: several chat ids may be listed, separated by commas
    chats = [x.strip() for x in os.environ.get('TELEGRAM_CHAT_ID', '').split(',') if x.strip()]
    if not token or not chats:
        log('no telegram secrets; would send:', text)
        return
    for chat in chats:
        try:
            post(f'https://api.telegram.org/bot{token}/sendMessage',
                 {'chat_id': chat, 'text': text, 'disable_web_page_preview': True}, referer='')
        except Exception as e:
            log('telegram failed', type(e).__name__, e)


def day_label(day):
    t = datetime.date.fromisoformat(day)
    return f"{t.month}/{t.day}({'월화수목금토일'[t.weekday()]})"


def main():
    try:
        state = json.load(open(STATE))
    except (OSError, ValueError):
        state = {}
    now = datetime.datetime.now(KST)
    items = state.get('_items')
    # item settings (new items, open times) are re-read once a minute; the days every check
    if not items or now.timestamp() - state.get('_full', 0) >= 60:
        items = [{'bizItemId': str(i['bizItemId']), 'name': i.get('name'), 'isImp': i.get('isImp'),
                  'isClosedBooking': i.get('isClosedBooking'), 'bookableSettingJson': i.get('bookableSettingJson')}
                 for i in biz_items()]
        full = now.timestamp()
    else:
        full = state.get('_full', 0)
    if not items:
        log('no items read; keeping state')
        return
    first = not state
    new_state = {'_items': items, '_full': full}
    msgs = []
    for it in items:
        iid, name = it['bizItemId'], it.get('name') or ''
        prev = state.get(iid)
        link = ITEM_PAGE.format(item=iid)
        if not is_open(it, now):
            when = (it.get('bookableSettingJson') or {}).get('openDateTime') or ''
            log(name, 'not open', when)
            new_state[iid] = {'live': False}
            if prev is None and not first and it.get('isImp') is not False:
                msgs.append(f'🆕 데시디자인 새 예약 항목: {name}' + (f'\n오픈 {when[5:16].replace("T", " ")}' if when else '') + '\n' + link)
            continue
        free = free_days(iid, now)
        if free is None:
            log(name, 'schedule unreadable')
            if prev:
                new_state[iid] = prev  # keep the old state so nothing is alerted twice
            continue
        log(name, 'free days', len(free), dict(sorted(free.items())[:10]))
        new_state[iid] = {'live': True, 'free': free}
        if first:
            continue  # first look: learn quietly
        if prev is None or not prev.get('live'):
            if free:
                msgs.append(f'🔔 데시디자인 예약 오픈: {name}\n자리 있는 날: '
                            + ', '.join(f'{day_label(d)} {n}자리' for d, n in sorted(free.items())[:15]) + '\n' + link)
            continue
        for d, n in sorted(free.items()):
            if d not in prev.get('free', {}):
                msgs.append(f'🔔 데시디자인 빈자리 {day_label(d)} {n}자리\n{name}\n{link}')
    for text in msgs:
        telegram(text)
        log('alert sent', text.splitlines()[0])
    json.dump(new_state, open(STATE, 'w'), ensure_ascii=False)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:  # keep the loop going; the log shows what broke
        log('error', type(e).__name__, e)
    with open('desi-log.txt', 'a') as f:
        f.write(datetime.datetime.now(KST).isoformat(timespec='seconds') + ' ' + ' | '.join(LOG) + '\n')
