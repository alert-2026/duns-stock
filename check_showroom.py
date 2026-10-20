"""Watches the Duns showroom Naver booking page and sends a Telegram alert when booking opens and whenever a
visit time frees up again (a cancellation). Run by .github/workflows/showroom.yml; state in showroom-state.json."""
import datetime, json, os, urllib.request

BIZ = '1638569'
PAGE = f'https://m.booking.naver.com/booking/12/bizes/{BIZ}'
# alerts link straight to the item's date/time page (samee asked on 10/20); startDate picks the day when Naver honours it
ITEM_PAGE = PAGE + '/items/{item}?startDate={day}'
UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148'
STATE = os.environ.get('SHOWROOM_STATE', 'showroom-state.json')
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


def shop_visible():
    """On 10/20 the item opened at 11:00 but the shop itself was still hidden (business is null), so the page
    showed an error; booking is only really possible once the shop shows up."""
    q = 'query business($input: BusinessParams) { business(input: $input) { businessId } }'
    return bool(gql('business', q, {'input': {'businessId': BIZ, 'lang': 'ko', 'projections': 'RESOURCE'}}).get('business'))


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


def free_slots(item_id, now, booked_needed=False):
    """Free times; with booked_needed, None unless someone has booked (proof booking really works)."""
    q = ('query hourlySchedule($scheduleParams: ScheduleParams) { schedule(input: $scheduleParams) '
         '{ bizItemSchedule { hourly { unitStartTime unitStock unitBookingCount isUnitSaleDay isUnitBusinessDay } } } }')
    d = gql('hourlySchedule', q, {'scheduleParams': {
        'businessTypeId': 12, 'businessId': BIZ, 'bizItemId': str(item_id),
        'startDateTime': now.strftime('%Y-%m-%dT00:00:00'),
        'endDateTime': (now + datetime.timedelta(days=90)).strftime('%Y-%m-%dT23:59:59'),
        'fixedTime': True, 'includesHolidaySchedules': True}})
    hourly = (((d.get('schedule') or {}).get('bizItemSchedule') or {}).get('hourly'))
    if hourly is None:
        return None
    now_str = now.strftime('%Y-%m-%d %H:%M')
    if not any(h.get('unitBookingCount') for h in hourly) and booked_needed:
        return None
    return sorted(h['unitStartTime'][:16] for h in hourly
                  if (h.get('unitStock') or 0) > (h.get('unitBookingCount') or 0)
                  and h.get('isUnitSaleDay') is not False and h.get('isUnitBusinessDay') is not False
                  and h['unitStartTime'][:16] > now_str)


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


def by_day(slots, limit=40, item=None):
    """'10/21(수) 11:00, 11:15' per line, each followed by a link to that day when item is given."""
    days = {}
    for s in slots:
        days.setdefault(s[:10], []).append(s[11:16])
    lines = []
    for day, times in sorted(days.items()):
        t = datetime.date.fromisoformat(day)
        shown = ', '.join(times[:limit]) + (f' 외 {len(times) - limit}개' if len(times) > limit else '')
        lines.append(f"· {t.month}/{t.day}({'월화수목금토일'[t.weekday()]}) {shown}")
        if item:
            lines.append('  ' + ITEM_PAGE.format(item=item, day=day))
    return '\n'.join(lines)


def main():
    try:
        state = json.load(open(STATE))
    except (OSError, ValueError):
        state = {}
    now = datetime.datetime.now(KST)
    msgs, new_state = [], {}
    visible = shop_visible()
    for it in biz_items():
        iid, name = str(it['bizItemId']), it.get('name') or ''
        prev = state.get(iid)
        # the shop query may stay empty even after opening; bookings appearing also prove it is open
        slots = free_slots(iid, now, booked_needed=not visible) if is_open(it, now) else None
        if slots is None and prev and prev.get('live'):
            new_state[iid] = prev  # a failed read after opening; keep the old state so nothing is alerted twice
            continue
        if slots is None:
            log(name, 'not open yet', 'shop visible' if visible else 'shop hidden',
                (it.get('bookableSettingJson') or {}).get('openDateTime'))
            new_state[iid] = {'live': False}
            continue
        log(name, 'free', len(slots), slots[:8])
        new_state[iid] = {'live': True, 'free': slots}
        if prev is None:
            continue  # first look: learn quietly
        if not prev.get('live'):
            if slots:
                msgs.append(f'[예약 오픈] {name}\n빈자리 {len(slots)}개\n' + by_day(slots, 12, iid))
            continue
        new = [s for s in slots if s not in set(prev.get('free', []))]
        if new:
            msgs.append(f'[빈자리] {name}\n' + by_day(new, item=iid))
    if msgs:
        stamp = now.strftime('%m/%d %H:%M')
        telegram(f'🔔 던스 쇼룸 예약 ({stamp}, KST)\n\n' + '\n\n'.join(msgs))
        log('alert sent', len(msgs))
    json.dump(new_state, open(STATE, 'w'), ensure_ascii=False)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:  # keep the loop going; the log shows what broke
        log('error', type(e).__name__, e)
    with open('showroom-log.txt', 'a') as f:
        f.write(datetime.datetime.now(KST).isoformat(timespec='seconds') + ' ' + ' | '.join(LOG) + '\n')
