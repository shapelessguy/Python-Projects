import importlib
import os
import subprocess
import sys
import telegram
import asyncio
import traceback
import json
import requests
import pandas as pd
from datetime import datetime, timedelta
from utils import LEO_TOKEN, LEO_GROUP_ID, BLAME_LOGS_FILEPATH, BLAMES_FILEPATH


main_folder = os.path.dirname(os.path.dirname(__file__))
RoomServer_project_path = os.path.dirname(__file__)
WG_project_path = os.path.join(main_folder, 'WG')
sys.path.append(WG_project_path)


def get_week_number(date):
    return date.isocalendar()[1], date.year


def get_date_from_week_id(week_id_):
    d = f"{week_id_[1]}-W{week_id_[0]}"
    return datetime.strptime(d + '-1', "%Y-W%W-%w").date()


def get_last_announcement():
    last_announcement = None
    try:
        with open(os.path.join(os.path.dirname(__file__), 'announcements.txt'), 'r') as file:
            last_announcement = datetime.strptime(file.read().split('\n')[-2], "%Y-%m-%d-%H-%M-%S")
    except:
        pass
    if last_announcement is None:
        last_announcement = datetime.strptime("2000-01-01-00-00-00", "%Y-%m-%d-%H-%M-%S")
    return last_announcement, get_week_number(last_announcement)


async def send(chat_id, token, msg, document=None):
    try:
        bot = telegram.Bot(token=token)
        if document is None:
            await bot.send_message(chat_id=chat_id, text=msg, parse_mode="HTML")
        elif document is not None:
            await bot.send_document(chat_id=chat_id, document=document, caption=msg)
        print(f"Message '{msg}' sent.")
    except Exception:
        print('Error while trying to send telegram message')
        print(traceback.format_exc())


def reload_module(module_name):
    if module_name in sys.modules:
        module = importlib.reload(sys.modules[module_name])
    else:
        module = importlib.import_module(module_name)
    return module


async def set_announcement(last_announcement):
    try:
        subprocess.run(f'cd {WG_project_path} && git pull', shell=True, capture_output=True, text=True)
        with open(BLAME_LOGS_FILEPATH, 'r') as file:
            logs = json.load(file)
        execute_logic = reload_module('execute_logic')
        BAC_logic = reload_module('BAC_logic')
        get_history = BAC_logic.get_history
        generate_plan = execute_logic.generate_plan
        WgMembers = BAC_logic.WgMembers
        WgProps = BAC_logic.WgProps
        wg_members = {k: v for k, v in WgMembers.__dict__.items() if not k.startswith('__')}
        wg_props = [{'name': wg_members[k], **v, } for k, v in WgProps.__dict__.items() if not k.startswith('__')]

        emoticons = BAC_logic.emoticons
        now = datetime.combine(get_date_from_week_id(get_week_number(datetime.now().date())), datetime.min.time())
        blame_first_date = (now - timedelta(days=14)).date()
        blame_last_date = (now - timedelta(days=7)).date()
        hist_df = get_history()
        for e in wg_props:
            name = e['name']
            date = str(blame_first_date)
            blames, blamed_activity = get_blame(name, date, hist_df, logs)
            if len(blames) >= 2:
                with open(BLAMES_FILEPATH, 'r') as file:
                    blames_json = json.load(file)
                with open(BLAMES_FILEPATH, 'w') as file:
                    blames_json['entries'].append({'name': name, 'date': date})
                    json.dump(blames_json, file)

        text, week_schedule = generate_plan()
        hist_df = get_history()

        subprocess.run(f'cd {WG_project_path} && git add . && git commit -m "auto_update" && git push', shell=True, capture_output=True, text=True)
        await send(chat_id=LEO_GROUP_ID, token=LEO_TOKEN, msg=text, document=os.path.join(WG_project_path, 'cleaning_plan_leo6.xlsx'))

        with open(os.path.join(os.path.dirname(__file__), 'announcements.txt'), 'a+') as file:
            file.write(last_announcement.strftime("%Y-%m-%d-%H-%M-%S") + '\n')
        
        for e in wg_props:
            name = e['name']
            blames, blamed_activity = get_blame(name, str(blame_first_date), hist_df, logs)
            telegram_id = e['telegram_id']
            string = f'Hello {name}, this is the schedule for the next weeks, waiting for you!\n'
            for week_n in week_schedule:
                week_now = (now + timedelta(days=(week_n * 7))).date().strftime("%d/%m")
                week_plus_1 = (now + timedelta(days=((week_n + 1) * 7))).date().strftime("%d/%m")
                pre = 'Week RANGE: ACT\n'
                if week_n == 0:
                    pre = 'This week (RANGE): ACT\n'
                elif week_n == 1:
                    pre = 'Next week (RANGE): ACT\n'
                activity = week_schedule[week_n][name]
                string += pre.replace('RANGE', f'{week_now} - {week_plus_1}').replace('ACT', f' <b>{activity}</b> {emoticons[activity]}')
            if blamed_activity != 'Vacation':
                if len(blames) == 0:
                    string += f'\nCongratulations, you have no complaints for the week {blame_first_date}-{blame_last_date}!'
                else:
                    blamed_activity = f' ({blamed_activity})' if blamed_activity is not None else ''
                    string += f'\nYou got {len(blames)} complaints in the week {blame_first_date}-{blame_last_date}{blamed_activity}.'
                    if len(blames) >= 2:
                        string += f'\nUnfortunately you will have to compensate in the next weeks with more tasks.'
            string += f"\nQuick commands's overview:"
            string += f'\n - blame TASK  (ex: blame kitchen)'
            string += f'\n - warn TASK  (ex: warn management)'
            string += f'\n - vacation DATE  (ex: vacation 25-11-2024)'
            if telegram_id is not None:
                print('Msg sent:', string)
                await send(chat_id=telegram_id, token=LEO_TOKEN, msg=string)
    except Exception as e:
        print(e)
        print(traceback.format_exc())


async def update(now, last_announcement, id_last_announcement, forced=False):
    announce_at = 8  # hour of update
    masked_now = now - timedelta(hours=(announce_at))
    if get_week_number(masked_now) != id_last_announcement or forced:
        if masked_now > last_announcement or forced:
            print('ANNOUNCEMENTS', now)
            await set_announcement(now)
            last_announcement = now
            id_last_announcement = get_week_number(now)
    return last_announcement, id_last_announcement


URL = f"https://api.telegram.org/bot{LEO_TOKEN}"

def fetch_updates():
    try:
        response = requests.get(f"{URL}/getUpdates")
        updates = response.json()
        incoming = []

        if updates.get("result"):
            last_update_id = updates["result"][-1]["update_id"]
            requests.get(f"{URL}/getUpdates?offset={last_update_id + 1}")
            if len(updates['result']) == 0:
                return []
            for result in updates['result']:
                from_id = result['message']['from']['id']
                date = datetime.fromtimestamp(result['message']['date'])
                msg = result['message']['text']
                incoming.append([from_id, date, msg])
        else:
            return []
        return incoming
    except Exception:
        return []


async def recognize_blame(message, logs):
    id_, dt, msg = message
    msg = msg.lower().split()
    if len(msg) != 2:
        return False
    if msg[0] != 'blame':
        return False
    BAC_logic = reload_module('BAC_logic')
    activity = [v for k, v in BAC_logic.Activities.__dict__.items() if not k.startswith('__') and k != 'vacation' if v.lower() == msg[1]]
    if len(activity) == 0:
        return False
    activity = activity[0]
    WgMembers = BAC_logic.WgMembers
    WgProps = BAC_logic.WgProps
    wg_members = {k: v for k, v in WgMembers.__dict__.items() if not k.startswith('__')}
    wg_props = [{'name': wg_members[k], **v, } for k, v in WgProps.__dict__.items() if not k.startswith('__')]
    member_name = None
    for e in wg_props:
        if e['telegram_id'] == id_:
            member_name = e['name']
    if member_name is None:
        return False

    current_week = (dt - timedelta(days=dt.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    previous_week = (current_week - timedelta(days=dt.weekday() + 7)).strftime("%Y-%m-%d")
    logs[member_name] = logs.get(member_name, [])
    entry = {'date': str(previous_week), 'submitted': str(dt), 'blame': activity}
    for e in logs[member_name]:
        if entry['date'] == e['date'] and entry['blame'] == e['blame']:
            await send(chat_id=id_, token=LEO_TOKEN, msg="You have already submitted this feedback.")
            return True
    logs[member_name].append(entry)
    with open(BLAME_LOGS_FILEPATH, 'w') as file:
        json.dump(logs, file, indent=2)
    await send(chat_id=id_, token=LEO_TOKEN, msg="Thanks for your feedback!")
    print(f'Received blame from {member_name} -> {activity}')
    return True


async def recognize_warn(message, logs):
    id_, dt, msg = message
    msg = msg.lower().split()
    if len(msg) != 2:
        return False
    if msg[0] != 'warn':
        return False
    BAC_logic = reload_module('BAC_logic')
    activity = [v for k, v in BAC_logic.Activities.__dict__.items() if not k.startswith('__') and k != 'vacation' if v.lower() == msg[1]]
    if len(activity) == 0:
        return False
    activity = activity[0]
    WgMembers = BAC_logic.WgMembers
    WgProps = BAC_logic.WgProps
    wg_members = {k: v for k, v in WgMembers.__dict__.items() if not k.startswith('__')}
    wg_props = [{'name': wg_members[k], **v, } for k, v in WgProps.__dict__.items() if not k.startswith('__')]
    member_name = None
    for e in wg_props:
        if e['telegram_id'] == id_:
            member_name = e['name']
    if member_name is None:
        return False
    current_week = (dt - timedelta(days=dt.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    previous_week = (current_week - timedelta(days=dt.weekday() + 7)).strftime("%Y-%m-%d")
    BAC_logic = reload_module('BAC_logic')
    get_history = BAC_logic.get_history
    hist_df = get_history()
    
    filtered_row = hist_df[hist_df['Week'] == previous_week]
    name_to_warn = [k for k, v in filtered_row.to_dict().items() if (len(v.values()) > 0 and list(v.values())[0] == activity)]
    if len(name_to_warn) == 0:
        await send(chat_id=id_, token=LEO_TOKEN, msg=f"Nobody to warn..")
        return True
    name_to_warn = name_to_warn[0]
    warn_chat_id = [e['telegram_id'] for e in wg_props if e['name'] == name_to_warn]
    if len(warn_chat_id) > 0:
        warn_chat_id = warn_chat_id[0]
        await send(chat_id=warn_chat_id, token=LEO_TOKEN, msg=f"You received a warning for the task {activity}!!!")
    await send(chat_id=id_, token=LEO_TOKEN, msg=f"Warning for {activity} sent!")
    return True


async def recognize_vacation(message):
    id_, dt, msg = message
    msg = msg.lower().split()
    if len(msg) != 2:
        return False
    if msg[0] != 'vacation':
        return False
    BAC_logic = reload_module('BAC_logic')
    date = msg[1]
    WgMembers = BAC_logic.WgMembers
    WgProps = BAC_logic.WgProps
    wg_members = {k: v for k, v in WgMembers.__dict__.items() if not k.startswith('__')}
    wg_props = [{'name': wg_members[k], **v, } for k, v in WgProps.__dict__.items() if not k.startswith('__')]
    member_name = None
    for e in wg_props:
        if e['telegram_id'] == id_:
            member_name = e['name']
    if member_name is None:
        return False
    
    try:
        date = [z.strip() for x in date.split('-') for y in x.split('/') for z in y.split('.')]
        day, month, year = [int(x) for x in date]
        year = year + 2000 if year < 100 else year
        date_to_check = datetime(year, month, day)
        if date_to_check.weekday() != 0:
            await send(chat_id=message[0], token=LEO_TOKEN, msg="Date must be a Monday.")
            return True

        current_week = (dt - timedelta(days=dt.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        if date_to_check < current_week:
            await send(chat_id=message[0], token=LEO_TOKEN, msg="You cannot book a vacation in the past.")

        vacations = BAC_logic.get_vacations()
        for v in vacations['entries']:
            if member_name in v['names'] and v['day'] == day and v['month'] == month and v['year'] == year:
                await send(chat_id=message[0], token=LEO_TOKEN, msg="This vacation has already been booked.")
                return True
        
        next_week = (date_to_check + timedelta(days=dt.weekday() + 7)).strftime("%d-%m-%Y")
        date_to_check = date_to_check.strftime("%d-%m-%Y")
        vacations['entries'].append({'names': [member_name], 'day': day, 'month': month, 'year': year})
        BAC_logic.save_vacations(vacations)
        await send(chat_id=message[0], token=LEO_TOKEN, msg=f"You booked a vacation for the week {date_to_check} - {next_week}!")
    except Exception:
        print(traceback.format_exc())
        await send(chat_id=message[0], token=LEO_TOKEN, msg="Date is in the wrong format.")
    return True


async def recognize_ping(message):
    id_, dt, msg = message
    msg = msg.lower().split()
    if len(msg) == 1 and msg[0] == 'ping':
        await send(chat_id=id_, token=LEO_TOKEN, msg="I am here!")
        return True
    return False


async def process_message(message, logs):
    if await recognize_blame(message, logs):
        return
    if await recognize_warn(message, logs):
        return
    if await recognize_vacation(message):
        return
    if await recognize_ping(message):
        return
    await send(chat_id=message[0], token=LEO_TOKEN, msg="Sorry I don't get what you say.")


async def monitor_chats():
    with open(BLAME_LOGS_FILEPATH, 'r') as file:
        logs = json.load(file)
    while True:
        output = fetch_updates()
        for message in output:
            await process_message(message, logs)
        await asyncio.sleep(0.5)


def get_blame(name, now, hist_df, logs):
    filtered_row = hist_df[hist_df['Week'] == now]
    value = [list(v.values())[0] for k, v in filtered_row.to_dict().items() if k == name]
    if len(value) == 0:
        return [], None
    activity = value[0]
    blames = [k for k, v in logs.items() if len([j for j in v if (j['date'] == now and j['blame'] == activity)]) > 0]
    return blames, activity


def spawn_monitoring():
    asyncio.run(monitor_chats())


if __name__ == '__main__':
    # with open(BLAME_LOGS_FILEPATH, 'r') as file:
    #     logs = json.load(file)
    # BAC_logic = reload_module('BAC_logic')
    # get_history = BAC_logic.get_history
    # hist_df = get_history()
    # now = datetime.combine(get_date_from_week_id(get_week_number(datetime.now().date())), datetime.min.time())
    # prev_week_date = (now - timedelta(days=7)).date()
    # blames, activity = get_blame('Claudio', str(prev_week_date), hist_df, logs)

    import threading, time
    threading.Thread(target=spawn_monitoring).start()
    while True:
        time.sleep(1)
