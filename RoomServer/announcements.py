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
from datetime import date as date_
from openpyxl.styles import Alignment
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
        return True
    except Exception:
        print('Error while trying to send telegram message')
        print(traceback.format_exc())
    return False


def reload_module(module_name):
    if module_name in sys.modules:
        module = importlib.reload(sys.modules[module_name])
    else:
        module = importlib.import_module(module_name)
    return module


async def set_announcement(last_announcement, updated=False):
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
        now = datetime.now()
        now = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
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

        intro = '<b>🔄 PLAN UPDATED DURING THIS WEEK</b>\n' if updated else ''
        text, week_schedule = generate_plan()
        text = intro + text
        if not updated:
            text += "\n\nNote: If you want to swap your task with someone else's task, send on our private chat \"swap TASK DATE\", "
            text += "where the date refers to that weeks's Monday (format dd/mm/yy)."
            text += "\nYou can submit an anonymous complaint for one or more tasks of the previous week by sending \"blame TASK\"."
            text += "\nBefore blaming someone, please wait until Wednesday evening so that the person has time to recover their delayed duty."
            text += "\nIf a person receives at least 2 blames, they will need to recover the task in the future ☠️."
            text += "\nAlternatively, you can send a warning ⚠️ to that person by sending \"warn TASK\"."
            text += "\nYou can also send a message of appreciation 🌟 by sending \"praise TASK\" as well."
            text += "\nIf you need vacation for a week, you can send \"vacation DATE\"."
            text += "\nWhenever you have a WG expense 💰, send \"expense PRICE\", where the price is in format X.xx (e.g. 2.50)."
        hist_df = get_history()

        subprocess.run(f'cd {WG_project_path} && git add . && git commit -m "auto_update" && git push', shell=True, capture_output=True, text=True)
        await send(chat_id=LEO_GROUP_ID, token=LEO_TOKEN, msg=text, document=os.path.join(WG_project_path, 'cleaning_plan_leo6.xlsx'))
        print('Msg sent to LEO6:', text)

        with open(os.path.join(os.path.dirname(__file__), 'announcements.txt'), 'a+') as file:
            file.write(last_announcement.strftime("%Y-%m-%d-%H-%M-%S") + '\n')
        
        for e in wg_props:
            name = e['name']
            blames, blamed_activity = get_blame(name, str(blame_first_date), hist_df, logs)
            telegram_id = e['telegram_id']
            string = '<b>🔄 PLAN UPDATED DURING THIS WEEK</b>\n' if updated else ''
            string += f'Hello {name}, this is the schedule for the next weeks, waiting for you!\n'
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
            if blamed_activity != 'Vacation' and not updated:
                if len(blames) == 0:
                    string += f'\n👍 Congratulations, you have no complaints for the week ' +\
                              f'{blame_first_date.strftime("%d/%m")} - {blame_last_date.strftime("%d/%m")}!'
                else:
                    blamed_activity = f' ({blamed_activity})' if blamed_activity is not None else ''
                    string += f'\n⚠️ You got {len(blames)} complaints in the week {blame_first_date}-{blame_last_date}{blamed_activity}.'
                    if len(blames) >= 2:
                        string += f'\n☠️ Unfortunately you will have to compensate in the next weeks with more tasks.'
            if not updated:
                string += f"\nQuick commands's overview:"
                string += f'\n - <b>blame TASK</b>  (ex: blame kitchen)'
                string += f'\n - <b>warn TASK &lt;COMMENT&gt;</b>\n     (ex: warn management Bins are not clean)'
                string += f'\n - <b>praise TASK &lt;COMMENT&gt;</b>\n     (ex: praise bathrooms Toilets are fabulous)'
                string += f'\n - <b>swap TASK DATE</b>\n     (ex: swap floor 25/11/24)'
                string += f'\n - <b>vacation DATE</b>  (ex: vacation 25/11/24)'
                string += f'\n - <b>vacations</b>  (to check your vacations)'
                string += f'\n - <b>expense PRICE &lt;COMMENT&gt;</b>  (ex: expense 2.50 oil)'
            if name == 'Mara':
                string += f'\n - <b>expenses &lt;from INDEX&gt; </b>  (ex: expenses / expenses from 23)'
            if telegram_id is not None:
                print('Msg sent:', string)
                await send(chat_id=telegram_id, token=LEO_TOKEN, msg=string)
    except Exception as e:
        print(e)
        print(traceback.format_exc())


async def update(last_announcement=None, id_last_announcement=None, forced=False, updated=False):
    now = datetime.now()
    announce_at = 8  # hour of update
    masked_now = now - timedelta(hours=(announce_at))
    if forced or get_week_number(masked_now) != id_last_announcement:
        if forced or masked_now > last_announcement:
            print('ANNOUNCEMENTS', now)
            await set_announcement(now, updated)
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
    activity = [v for k, v in BAC_logic.Activities.__dict__.items() if not k.startswith('__') and k.lower() != 'vacation' if v.lower() == msg[1]]
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
    answer = False
    entry = {'date': str(previous_week), 'submitted': str(dt), 'blame': activity}
    for e in logs[member_name]:
        if entry['date'] == e['date'] and entry['blame'] == e['blame']:
            answer = await send(chat_id=id_, token=LEO_TOKEN, msg="❌ You have already submitted this feedback.")
            return True
    logs[member_name].append(entry)
    with open(BLAME_LOGS_FILEPATH, 'w') as file:
        json.dump(logs, file, indent=2)
    if answer:
        await send(chat_id=id_, token=LEO_TOKEN, msg="✅ Thanks for your feedback!")
    print(f'Received blame from {member_name} -> {activity}')
    return True


async def recognize_simple_request(message, log, type_, msg_to_send):
    id_, dt, msg = message
    msg = msg.split()
    if len(msg) < 2:
        return False
    if msg[0] != type_:
        return False
    activity_ = msg[1].lower()
    BAC_logic = reload_module('BAC_logic')
    activity = [v for k, v in BAC_logic.Activities.__dict__.items() if not k.startswith('__') and k.lower() != 'vacation' if v.lower() == activity_]
    if len(activity) == 0:
        return False
    comment = ' '.join(msg[2:])
    comment = f'\nComment: {comment}' if len(comment) > 0 else ''
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
    previous_week = (current_week - timedelta(days=7)).strftime("%Y-%m-%d")
    pw_format = (current_week - timedelta(days=7)).strftime("%d/%m")
    cw_format = current_week.strftime("%d/%m")
    BAC_logic = reload_module('BAC_logic')
    get_history = BAC_logic.get_history
    hist_df = get_history()
    
    filtered_row = hist_df[hist_df['Week'] == previous_week]
    name_to_warn = [k for k, v in filtered_row.to_dict().items() if (len(v.values()) > 0 and list(v.values())[0] == activity)]
    if len(name_to_warn) == 0:
        await send(chat_id=id_, token=LEO_TOKEN, msg=f"❌ Nobody to {type_}..")
        return True
    name_to_warn = name_to_warn[0]
    warn_chat_id = [e['telegram_id'] for e in wg_props if e['name'] == name_to_warn]
    answer = False
    if len(warn_chat_id) > 0:
        warn_chat_id = warn_chat_id[0]
        answer = await send(chat_id=warn_chat_id, token=LEO_TOKEN, msg=f"For the task {activity} (week {pw_format} - {cw_format}):\n{msg_to_send}{comment}")
    if answer:
        await send(chat_id=id_, token=LEO_TOKEN, msg=f"✅ {type_} message for {activity} (week {pw_format} - {cw_format}) sent!")
    return True


async def recognize_warn(message, logs):
    token, msg_to_send = 'warn', '⚠️ Watch out, you received a warning!'
    return await recognize_simple_request(message, logs, token, msg_to_send)


async def recognize_praise(message, logs):
    token, msg_to_send = 'praise', '🌟 Someone praised you &lt;3'
    return await recognize_simple_request(message, logs, token, msg_to_send)


async def recognize_vacation(message):
    id_, dt, msg = message
    msg = msg.lower().split()
    undo = False
    if len(msg) != 2:
        if len(msg) != 3 or msg[-1] != 'undo':
            return False
        undo = True
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
    except Exception:
        print(traceback.format_exc())
        await send(chat_id=message[0], token=LEO_TOKEN, msg="❌ Date is in the wrong format.")
        return True
    
    try:
        now = datetime.now()
        now = (now - timedelta(days=now.weekday()))
        date_to_check = datetime(year, month, day)

        current_week = (dt - timedelta(days=dt.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        if date_to_check < current_week:
            await send(chat_id=message[0], token=LEO_TOKEN, msg="❌ You cannot indicate a date in the past.")
            return True

        if date_to_check.weekday() != 0:
            await send(chat_id=message[0], token=LEO_TOKEN, msg="❌ Date must be a Monday.")
            return True
        this_week = now.date() == date_to_check.date()

        vacations = BAC_logic.get_vacations()
        next_week = (date_to_check + timedelta(days=dt.weekday() + 7)).strftime("%d/%m/%Y")
        date_to_check = date_to_check.strftime("%d/%m/%Y")

        if undo:
            deleted = False
            for i in range(len(vacations['entries'])):
                v = vacations['entries'][i]
                if member_name in v['names'] and v['day'] == day and v['month'] == month and v['year'] == year:
                    del vacations['entries'][i]
                    deleted = True
                    break
            if not deleted:
                await send(chat_id=message[0], token=LEO_TOKEN, msg="❌ This vacation has not been booked.")
                return True
            else:
                BAC_logic.save_vacations(vacations)
                updated_text = '\n🔄 A new plan is now getting generated..' if this_week else ''
                await send(chat_id=message[0], token=LEO_TOKEN, msg=f"✅ You unbooked your vacation for the week {date_to_check} - {next_week}.{updated_text}")
                if this_week:
                    await update(forced=True, updated=True)
                    print('updated')
                return True
        else:
            for v in vacations['entries']:
                if member_name in v['names'] and v['day'] == day and v['month'] == month and v['year'] == year:
                    await send(chat_id=message[0], token=LEO_TOKEN, msg="❌ This vacation has already been booked.")
                    return True
            vacations['entries'].append({'names': [member_name], 'day': day, 'month': month, 'year': year, 'n_weeks': 1})
            BAC_logic.save_vacations(vacations)
            updated_text = '\n🔄 A new plan is now getting generated..' if this_week else ''
            await send(chat_id=message[0], token=LEO_TOKEN, msg=f"✅ You booked a vacation for the week {date_to_check} - {next_week}!{updated_text}")
            if this_week:
                await update(forced=True, updated=True)
                print('updated')
    except Exception:
        print(traceback.format_exc())
        await send(chat_id=message[0], token=LEO_TOKEN, msg="❌ Unknown error.")
    return True


async def recognize_myvacations(message):
    id_, dt, msg = message
    msg = msg.lower().split()
    if len(msg) != 1:
        return False
    if msg[0] != 'vacations':
        return False
    BAC_logic = reload_module('BAC_logic')
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
    current_week = (dt - timedelta(days=dt.weekday())).date()
    vacations = BAC_logic.get_vacations()
    my_vacations = 'Your vacations:\n'
    found = False
    for v in vacations['entries']:
        date = date_(v['year'], v['month'], v['day'])
        next_week = date + timedelta(weeks=1)
        if member_name in v['names'] and date >= current_week:
            my_vacations += f'- {date.strftime("%d/%m/%Y")} - {next_week.strftime("%d/%m/%Y")}\n'
            found = True
    my_vacations = my_vacations if found else "You don't have any vacation booked."
    await send(chat_id=message[0], token=LEO_TOKEN, msg=my_vacations)
    return True


async def recognize_expense(message):
    id_, dt, msg = message
    msg = msg.split()
    if len(msg) < 2:
        return False
    if msg[0].lower() != 'expense':
        return False
    price = msg[1]
    try:
        price = [y for x in price.split(',') for y in x.split('.')]
        price = [int(x) for x in price]
        assert 0 < len(price) <= 2
        if len(price) == 1:
            price.append(0)
        price_str = f"{price[0]}.{'0' * (2 - len(str(price[1])))}{price[1]}€"
        price = float(f'{price[0]}.{price[1]}')
    except Exception:
        print(traceback.format_exc())
        await send(chat_id=message[0], token=LEO_TOKEN, msg="❌ Price is in the wrong format.")
        return True

    reason = ' '.join(msg[2:])
    BAC_logic = reload_module('BAC_logic')
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
    
    current_week = (dt - timedelta(days=dt.weekday())).date()
    expenses = BAC_logic.get_expenses()
    index = len(expenses['entries'])
    expenses['entries'].append({'index': index, 'name': member_name, 'price': price, 'reason': reason,
                                'year': current_week.year, 'month': current_week.month, 'day': current_week.day})
    BAC_logic.save_expenses(expenses)
    reason_str = f' "{reason}"' if reason != '' else ''
    await send(chat_id=message[0], token=LEO_TOKEN, msg=f'✅ Your expense{reason_str} for {price_str} has been recorded.')
    return True


async def recognize_expenses(message):
    id_, dt, msg = message
    msg = msg.split()
    if len(msg) != 1:
        if len(msg) != 3 or msg[1].lower() != 'from':
            return False
    if msg[0].lower() != 'expenses':
        return False

    in_index = 0
    if len(msg) == 3:
        try:
            in_index = int(msg[2])
            assert in_index >= 0
        except Exception:
            await send(chat_id=message[0], token=LEO_TOKEN, msg="❌ Wrong index.")
            return True

    BAC_logic = reload_module('BAC_logic')
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
    
    expenses = BAC_logic.get_expenses()
    expenses_list = [
        [e['index'], e['name'], e['price'], e['reason'], date_(day=e['day'], month=e['month'], year=e['year']).strftime("%d/%m/%y")]
        for e in expenses['entries'] if e['index'] >= in_index
    ]
    expenses_df = pd.DataFrame(data=expenses_list, columns=['Index', 'Name', 'Price', 'Reason', 'Date'])

    totals_by_name = expenses_df.groupby("Name")["Price"].sum().reset_index()
    totals_by_name.columns = ["Name", "Total Price"]

    with pd.ExcelWriter("expenses.xlsx", engine="openpyxl") as writer:
        expenses_df.to_excel(writer, sheet_name="Expenses", index=False)
        totals_by_name.to_excel(writer, sheet_name="Totals", index=False)
        sheets = [writer.sheets["Expenses"], writer.sheets["Totals"]]
        
        for sheet in sheets:
            for col in sheet.columns:
                max_length = 15
                col_letter = col[0].column_letter
                sheet.column_dimensions[col_letter].width = max_length
            for row in sheet.iter_rows(min_row=1, max_row=sheet.max_row, min_col=1, max_col=sheet.max_column):
                for cell in row:
                    cell.alignment = Alignment(horizontal="center", vertical="center")

    await send(chat_id=message[0], token=LEO_TOKEN, msg=f'All the expenses from index {in_index}.', document="expenses.xlsx")
    return True


async def recognize_swap(message):
    id_, dt, msg = message
    msg = msg.lower().split()
    if len(msg) != 3:
        return False
    if msg[0] != 'swap':
        return False
    activity_ = msg[1].lower()
    BAC_logic = reload_module('BAC_logic')
    activity = [v for k, v in BAC_logic.Activities.__dict__.items() if not k.startswith('__') and k.lower() != 'vacation' if v.lower() == activity_]
    if len(activity) == 0:
        return False
    activity = activity[0]
    date = msg[2]

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
    except Exception:
        print(traceback.format_exc())
        await send(chat_id=message[0], token=LEO_TOKEN, msg="❌ Date is in the wrong format.")
        return True
    
    try:
        now = datetime.now()
        now = (now - timedelta(days=now.weekday()))
        date_to_check = datetime(year, month, day)

        current_week = (dt - timedelta(days=dt.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        if date_to_check < current_week:
            await send(chat_id=message[0], token=LEO_TOKEN, msg="❌ You cannot indicate a date in the past.")
            return True

        if date_to_check.weekday() != 0:
            await send(chat_id=message[0], token=LEO_TOKEN, msg="❌ Date must be a Monday.")
            return True
        this_week = now.date() == date_to_check.date()

        swaps = BAC_logic.get_swaps()
        next_week = (date_to_check + timedelta(days=dt.weekday() + 7)).strftime("%d/%m/%Y")
    
        get_plan = BAC_logic.get_plan
        plan_df = get_plan()
        filtered_row = plan_df[plan_df['Week'] == date_to_check.strftime("%Y-%m-%d")]
        date_to_check = date_to_check.strftime("%d/%m/%Y")
        name_to_swap = [k for k, v in filtered_row.to_dict().items() if (len(v.values()) > 0 and list(v.values())[0] == activity)]
        try:
            my_activity = [list(v.values())[0] for k, v in filtered_row.to_dict().items() if (len(v.values()) > 0 and k == member_name)]
            my_activity = [v for k, v in BAC_logic.Activities.__dict__.items() if not k.startswith('__') and k.lower() != 'vacation' if v == my_activity[0]][0]
            if activity == my_activity:
                await send(chat_id=id_, token=LEO_TOKEN, msg=f"❌ You cannot swap {my_activity} with {activity}..")
                return True
        except Exception:
            print(traceback.format_exc())
            name_to_swap = []
        if len(name_to_swap) == 0:
            await send(chat_id=id_, token=LEO_TOKEN, msg=f"❌ You cannot swap with {activity}..")
            return True
        name_to_swap = name_to_swap[0]
        swaps['entries'].append({'name1': member_name, 'name2': name_to_swap, 'day': day, 'month': month, 'year': year})
        BAC_logic.save_swaps(swaps)
        updated_text = '\n🔄 A new plan is now getting generated..' if this_week else ''
        await send(chat_id=message[0], token=LEO_TOKEN, msg=f"✅ Activity {my_activity} swapped with {activity} for the week {date_to_check} - {next_week}!{updated_text}")
        if this_week:
            await update(forced=True, updated=True)
    except Exception:
        print(traceback.format_exc())
        await send(chat_id=message[0], token=LEO_TOKEN, msg="❌ Unknown error.")
    return True


async def recognize_ping(message):
    id_, dt, msg = message
    msg = msg.lower().split()
    if len(msg) == 1 and msg[0] == 'ping':
        await send(chat_id=id_, token=LEO_TOKEN, msg=f"✅ I am here! Chat-id: {id_}")
        return True
    return False


async def process_message(message, logs):
    if await recognize_blame(message, logs):
        return
    if await recognize_warn(message, logs):
        return
    if await recognize_praise(message, logs):
        return
    if await recognize_expense(message):
        return
    if await recognize_expenses(message):
        return
    if await recognize_swap(message):
        return
    if await recognize_myvacations(message):
        return
    if await recognize_vacation(message):
        return
    if await recognize_ping(message):
        return
    await send(chat_id=message[0], token=LEO_TOKEN, msg="❌ Sorry I didn't get what you wrote :(")


async def monitor_chats(signal):
    with open(BLAME_LOGS_FILEPATH, 'r') as file:
        logs = json.load(file)
    while not signal['kill']:
        output = fetch_updates()
        for message in output:
            await process_message(message, logs)
        await asyncio.sleep(0.5)


def get_blame(name, now, hist_df, logs):
    filtered_row = hist_df[hist_df['Week'] == now]
    dict_ = filtered_row.to_dict()
    if len(dict_[name]) == 0:
        return [], None
    value = [list(v.values())[0] for k, v in dict_.items() if k == name]
    if len(value) == 0:
        return [], None
    activity = value[0]
    blames = [k for k, v in logs.items() if len([j for j in v if (j['date'] == now and j['blame'] == activity)]) > 0]
    return blames, activity


def spawn_monitoring(signal):
    asyncio.run(monitor_chats(signal))


if __name__ == '__main__':
    pass
