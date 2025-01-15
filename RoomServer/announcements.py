import telebot
from telebot import types
import importlib
import os
import subprocess
import sys
import traceback
import json
import pandas as pd
import threading
import time
from datetime import datetime, timedelta
from datetime import date as date_
from openpyxl.styles import Alignment
from telegram_bot_calendar import DetailedTelegramCalendar, LSTEP
from utils import LEO_TOKEN, LEO_GROUP_ID, BLAME_LOGS_FILEPATH, BLAMES_FILEPATH


main_folder = os.path.dirname(os.path.dirname(__file__))
RoomServer_project_path = os.path.dirname(__file__)
WG_project_path = os.path.join(main_folder, 'WG')
sys.path.append(WG_project_path)
temp_data = {}
error_msg = "❌ Shit I messed up internally! Let's try again shall we?"
l_signal = {}
debug_flag = False
BREAK_TOKEN = '↩️'


def get_general_metadata():
    BAC_logic = reload_module('BAC_logic')
    execute_logic = reload_module('execute_logic')
    WgMembers = BAC_logic.WgMembers
    WgProps = BAC_logic.WgProps
    emoticons = BAC_logic.emoticons
    get_history = BAC_logic.get_history
    get_swaps = BAC_logic.get_swaps
    save_swaps = BAC_logic.save_swaps
    get_plan = BAC_logic.get_plan
    get_vacations = BAC_logic.get_vacations
    save_vacations = BAC_logic.save_vacations
    get_expenses = BAC_logic.get_expenses
    save_expenses = BAC_logic.save_expenses
    generate_plan = execute_logic.generate_plan
    wg_members = {k: v for k, v in WgMembers.__dict__.items() if not k.startswith('__')}
    wg_props = [{'name': wg_members[k], **v, } for k, v in WgProps.__dict__.items() if not k.startswith('__')]
    activities = [v for k, v in BAC_logic.Activities.__dict__.items() if not k.startswith('__') and k.lower() != 'vacation']
    with open(BLAME_LOGS_FILEPATH, 'r') as file:
        logs = json.load(file)
    functions = {'get_history': get_history, 'get_swaps': get_swaps, 'save_swaps': save_swaps, 'get_plan': get_plan,
                 'get_vacations': get_vacations, 'save_vacations': save_vacations, 'get_expenses': get_expenses,
                 'save_expenses': save_expenses, 'generate_plan': generate_plan}
    metadata = {'functions': functions, 'wg_members': wg_members, 'wg_props': wg_props,
                'activities': activities, 'blame_logs': logs, 'emoticons': emoticons}
    return metadata


def get_message_md(message, md):
    req_dt = datetime.fromtimestamp(message.date)

    sender_name = None
    for e in md['wg_props']:
        if e['telegram_id'] == message.chat.id:
            sender_name = e['name']
    if sender_name is None:
        return None, None, req_dt
    
    sender_activity = [v for v in md['activities'] if v.lower() == message.text.lower()]
    if len(sender_activity) == 0:
        return None, sender_name, req_dt
    sender_activity = sender_activity[0]

    return sender_activity, sender_name, req_dt


def break_handler(message):
    new_request(message, "How can I be your hero today?")


def blame_handler1(message):
    if not set_current_id(message):
        return
    try:
        md = get_general_metadata()
        activities = md['activities']
        sender_activity, sender_name, req_dt = get_message_md(message, md)
        if req_dt.weekday() < 3 and message.data['action'].id == 'blame':
            new_request(message, "❌ Calm down Rocky.. wait until end of Wednesday at least!")
            return
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
        for i in range(int((len(activities) + 0.99) / 2)):
            if len(activities) > 2*i + 1:
                markup.row(activities[2*i], activities[2*i + 1])
            else:
                markup.row(activities[2*i])
        temp_data[message.chat.id] = {**temp_data.get(message.chat.id, {}), 'data': message.data, 'md': md}
        bot.send_message(message.chat.id, "Responsible of which activity??", reply_markup=markup)
        if message.data['action'].id == 'blame':
            bot.register_next_step_handler(message, blame_handler2)
        else:
            bot.register_next_step_handler(message, direct_msg_handler1)
    except:
        print(traceback.format_exc())
        new_request(message, error_msg)


def blame_handler2(message):
    if not set_current_id(message):
        return
    try:
        target_activity, sender_name, req_dt = get_message_md(message, temp_data[message.chat.id]['md'])
        if target_activity is None:
            new_request(message, error_msg)
            return
        logs = temp_data[message.chat.id]['md']['blame_logs']
        current_week = (req_dt - timedelta(days=req_dt.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        previous_week = (current_week - timedelta(7)).strftime("%Y-%m-%d")
        logs[sender_name] = logs.get(sender_name, [])

        entry = {'date': str(previous_week), 'submitted': str(req_dt), 'blame': target_activity}
        for e in logs[sender_name]:
            if entry['date'] == e['date'] and entry['blame'] == e['blame']:
                new_request(message, "❌ You have already submitted this feedback.")
                return
        logs[sender_name].append(entry)
        with open(BLAME_LOGS_FILEPATH, 'w') as file:
            json.dump(logs, file, indent=2)
        new_request(message, "✅ Thanks for your feedback!")
    except:
        print(traceback.format_exc())
        new_request(message, error_msg)


def direct_msg_handler1(message):
    if not set_current_id(message):
        return
    try:
        target_activity, sender_name, req_dt = get_message_md(message, temp_data[message.chat.id]['md'])
        if target_activity is None:
            new_request(message, error_msg)
            return
        msg_type = temp_data[message.chat.id]['data']['action'].id  # blame, warn, praise
        get_history = temp_data[message.chat.id]['md']['functions']['get_history']
        hist_df = get_history()
        current_week = (req_dt - timedelta(days=req_dt.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        previous_week = (current_week - timedelta(7)).strftime("%Y-%m-%d")
        pw_format = (current_week - timedelta(days=7)).strftime("%d/%m")
        cw_format = current_week.strftime("%d/%m")
        filtered_row = hist_df[hist_df['Week'] == previous_week]
        target_name = [k for k, v in filtered_row.to_dict().items() if (len(v.values()) > 0 and list(v.values())[0] == target_activity)]
        if len(target_name) == 0:
            new_request(message, f"❌ Nobody to {msg_type} my friend.")
            return
        target_name = target_name[0]
        if sender_name == target_name:
            new_request(message, f"❌ Don't be silly!! It was you..")
            return
        target_chat_id = [e['telegram_id'] for e in temp_data[message.chat.id]['md']['wg_props'] if e['name'] == target_name]

        if len(target_chat_id) > 0:
            target_chat_id = target_chat_id[0]
            temp_data[message.chat.id]['target_chat_id'] = target_chat_id
            add = '⚠️ Watch out, you received a warning!' if msg_type == 'warn' else '🌟 Someone praised you &lt;3'
            temp_data[message.chat.id]['msg_to_send'] = f"For the task {target_activity} (week {pw_format} - {cw_format}):\n{add} - |COMMENT|"
            temp_data[message.chat.id]['msg_to_read'] = f"✅ Alright! For the task {target_activity} (week {pw_format} - {cw_format}) you sent the message:\n{add} - |COMMENT|"
            bot.send_message(message.chat.id, "Don't be lazy and leave a comment:", reply_markup=types.ReplyKeyboardRemove())
            bot.register_next_step_handler(message, direct_msg_handler2)
    except:
        print(traceback.format_exc())
        new_request(message, error_msg)


def direct_msg_handler2(message):
    if not set_current_id(message):
        return
    try:
        target_chat_id = temp_data[message.chat.id]['target_chat_id']
        bot.send_message(target_chat_id, f"{temp_data[message.chat.id]['msg_to_send'].replace('|COMMENT|', message.text)}")
        new_request(message, f"{temp_data[message.chat.id]['msg_to_read'].replace('|COMMENT|', message.text)}")
    except:
        print(traceback.format_exc())
        new_request(message, error_msg)


def swap_handler1(message):
    if not set_current_id(message):
        return
    try:
        md = get_general_metadata()
        temp_data[message.chat.id] = {**temp_data.get(message.chat.id, {}), 'data': message.data, 'md': md}
        _, sender_name, req_dt = get_message_md(message, md)
        if sender_name is None:
            new_request(message, error_msg)
            return
        temp_data[message.chat.id]['sender_name'] = sender_name
        temp_data[message.chat.id]['req_dt'] = req_dt
        activities = md['activities']
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
        for i in range(int((len(activities) + 0.99) / 2)):
            if len(activities) > 2*i + 1:
                markup.row(activities[2*i], activities[2*i + 1])
            else:
                markup.row(activities[2*i])
        bot.send_message(
            message.chat.id,
            f"What activity do u wanna swap yours with?",
            reply_markup=markup
        )
        bot.register_next_step_handler(message, swap_handler2)
    except:
        print(traceback.format_exc())
        new_request(message, error_msg)

def swap_handler2(message):
    if not set_current_id(message):
        return
    try:
        calendar, step = DetailedTelegramCalendar().build()
        temp_data[message.chat.id]['target_activity'] = message.text
        temp_data[message.chat.id]['calendar_title'] = "Which week are you referring to?"
        temp_data[message.chat.id]['calendar_on_result'] = swap_handler3
        bot.send_message(
            message.chat.id,
            f"{temp_data[message.chat.id]['calendar_title']} Select {LSTEP[step]}",
            reply_markup=calendar
        )
    except:
        print(traceback.format_exc())
        new_request(message, error_msg)

def swap_handler3(message):
    if not set_current_id(message):
        return
    try:
        sender_name = temp_data[message.chat.id]['sender_name']
        req_dt = temp_data[message.chat.id]['req_dt']
        md = temp_data[message.chat.id]['md']
        date = temp_data[message.chat.id]['calendar_result']
        target_activity = temp_data[message.chat.id]['target_activity']
        year, month, day = date.year, date.month, date.day
    
        now = datetime.now()
        now = (now - timedelta(days=now.weekday()))
        date_to_check = datetime(year, month, day)

        current_week = (req_dt - timedelta(days=req_dt.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        if date_to_check < current_week:
            new_request(message, "❌ Dude, it's too late now.")
            return

        if date_to_check.weekday() != 0:
            new_request(message, "❌ Date must be a Monday.")
            return
        this_week = now.date() == date_to_check.date()

        swaps = md['functions']['get_swaps']()
        plan_df = md['functions']['get_plan']()
        next_week = (date_to_check + timedelta(days=req_dt.weekday() + 7)).strftime("%d/%m/%Y")
    
        filtered_row = plan_df[plan_df['Week'] == date_to_check.strftime("%Y-%m-%d")]
        date_to_check = date_to_check.strftime("%d/%m/%Y")
        name_to_swap = [k for k, v in filtered_row.to_dict().items() if (len(v.values()) > 0 and list(v.values())[0] == target_activity)]
        try:
            sender_activity = [list(v.values())[0] for k, v in filtered_row.to_dict().items() if (len(v.values()) > 0 and k == sender_name)]
            sender_activity = [v for v in md['activities'] if v == sender_activity[0]][0]
            if sender_activity == target_activity:
                new_request(message, "❌ Dude, are you serious?")
                return
        except Exception:
            print(traceback.format_exc())
            name_to_swap = []
        if len(name_to_swap) == 0:
            new_request(message, f"❌ You cannot swap with {target_activity}.")
            return
        name_to_swap = name_to_swap[0]
        entry = {'name1': sender_name, 'name2': name_to_swap, 'day': day, 'month': month, 'year': year}
        if entry in swaps['entries']:
            new_request(message, "❌ Dude, you already swapped with this activity.")
            return
        swaps['entries'].append(entry)
        md['functions']['save_swaps'](swaps)
        updated_text = '\n🔄 A new plan is now getting generated..' if this_week else ''
        new_request(message, f"✅ Activity {sender_activity} swapped with {target_activity} for the week {date_to_check} - {next_week}!{updated_text}")
        if this_week:
            l_signal['set_announcement'] = {'updated': True}
    except Exception:
        print(traceback.format_exc())
        new_request(message, error_msg)


def vacations_handler1(message):
    if not set_current_id(message):
        return
    try:
        md = get_general_metadata()
        temp_data[message.chat.id] = {**temp_data.get(message.chat.id, {}), 'data': message.data, 'md': md}
        _, sender_name, req_dt = get_message_md(message, md)
        if sender_name is None:
            new_request(message, error_msg)
            return
        current_week = (req_dt - timedelta(days=req_dt.weekday())).date()
        vacations = md['functions']['get_vacations']()
        my_vacations = 'Your vacations:\n'
        found = False
        for v in vacations['entries']:
            date = date_(v['year'], v['month'], v['day'])
            next_week = date + timedelta(weeks=1)
            if sender_name in v['names'] and date >= current_week:
                my_vacations += f'- {date.strftime("%d/%m/%Y")} - {next_week.strftime("%d/%m/%Y")}\n'
                found = True
        my_vacations = my_vacations if found else "You don't have any vacation booked."
        new_request(message, my_vacations)
        return True
    except Exception:
        new_request(message, error_msg)
        return


def vacation_handler1(message):
    if not set_current_id(message):
        return
    try:
        md = get_general_metadata()
        temp_data[message.chat.id] = {**temp_data.get(message.chat.id, {}), 'data': message.data, 'md': md}
        calendar, step = DetailedTelegramCalendar().build()
        temp_data[message.chat.id]['target_activity'] = message.text
        temp_data[message.chat.id]['calendar_title'] = "When do you wanna take vacation?"
        temp_data[message.chat.id]['calendar_on_result'] = vacation_handler2
        bot.send_message(
            message.chat.id,
            f"{temp_data[message.chat.id]['calendar_title']} Select {LSTEP[step]}",
            reply_markup=calendar
        )
    except Exception:
        new_request(message, error_msg)
        return


def vacation_handler2(message):
    if not set_current_id(message):
        return
    try:
        _, sender_name, req_dt = get_message_md(message, temp_data[message.chat.id]['md'])
        md = temp_data[message.chat.id]['md']
        if sender_name is None:
            new_request(message, error_msg)
            return
        date = temp_data[message.chat.id]['calendar_result']
        year, month, day = date.year, date.month, date.day

        now = datetime.now()
        now = (now - timedelta(days=now.weekday()))
        date_to_check = datetime(year, month, day)

        current_week = (req_dt - timedelta(days=req_dt.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        if date_to_check < current_week:
            new_request(message, "❌ Dude, you cannot indicate a date in the past!")
            return

        if date_to_check.weekday() != 0:
            new_request(message, "❌ Dude, date must be a Monday!")
            return
        this_week = now.date() == date_to_check.date()

        vacations = md['functions']['get_vacations']()
        next_week = (date_to_check + timedelta(days=req_dt.weekday() + 7)).strftime("%d/%m/%Y")
        date_to_check = date_to_check.strftime("%d/%m/%Y")

        for v in vacations['entries']:
            if sender_name in v['names'] and v['day'] == day and v['month'] == month and v['year'] == year:
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
                markup.row("NO", "YES")
                bot.send_message(message.chat.id, f"This vacation has already been booked.. do you want to unbook it?", reply_markup=markup)
                bot.register_next_step_handler(message, vacation_handler3)
                return
        vacations['entries'].append({'names': [sender_name], 'day': day, 'month': month, 'year': year, 'n_weeks': 1})
        md['functions']['save_vacations'](vacations)
        updated_text = '\n🔄 A new plan is now getting generated..' if this_week else ''
        new_request(message, f"✅ You booked a vacation for the week {date_to_check} - {next_week}!{updated_text}")
        if this_week:
            l_signal['set_announcement'] = {'updated': True}
    except Exception:
        print(traceback.format_exc())
        new_request(message, error_msg)


def vacation_handler3(message):
    if not set_current_id(message):
        return
    try:
        if message.text != 'YES':
            new_request(message, f"Alright, then what the hell do you want??")
            return
        md = temp_data[message.chat.id]['md']
        _, sender_name, req_dt = get_message_md(message, md)
        date = temp_data[message.chat.id]['calendar_result']
        year, month, day = date.year, date.month, date.day

        now = datetime.now()
        now = (now - timedelta(days=now.weekday()))
        date_to_check = datetime(year, month, day)
        this_week = now.date() == date_to_check.date()

        vacations = md['functions']['get_vacations']()
        next_week = (date_to_check + timedelta(days=req_dt.weekday() + 7)).strftime("%d/%m/%Y")
        date_to_check = date_to_check.strftime("%d/%m/%Y")

        for i in range(len(vacations['entries'])):
            v = vacations['entries'][i]
            if sender_name in v['names'] and v['day'] == day and v['month'] == month and v['year'] == year:
                del vacations['entries'][i]
                break
        md['functions']['save_vacations'](vacations)
        updated_text = '\n🔄 A new plan is now getting generated..' if this_week else ''
        new_request(message, f"✅ You unbooked your vacation for the week {date_to_check} - {next_week}.{updated_text}")
        if this_week:
            l_signal['set_announcement'] = {'updated': True}
        return True
    except Exception:
        print(traceback.format_exc())
        new_request(message, error_msg)


def expense_handler1(message):
    if not set_current_id(message):
        return
    try:
        md = get_general_metadata()
        temp_data[message.chat.id] = {**temp_data.get(message.chat.id, {}), 'data': message.data, 'md': md}
        bot.send_message(message.chat.id, f"How much did you pay?", reply_markup=types.ReplyKeyboardRemove())
        bot.register_next_step_handler(message, expense_handler2)
    except Exception:
        print(traceback.format_exc())
        new_request(message, error_msg)


def expense_handler2(message):
    if not set_current_id(message):
        return
    price = message.text
    try:
        price = [y for x in price.split(',') for y in x.split('.')]
        price = [int(x) for x in price]
        assert 0 < len(price) <= 2
        if len(price) == 1:
            price.append(0)
        price_str = f"{price[0]}.{'0' * (2 - len(str(price[1])))}{price[1]}€"
        price = float(f'{price[0]}.{price[1]}')
        temp_data[message.chat.id]['expense'] = price
        temp_data[message.chat.id]['expense_str'] = price_str

        bot.send_message(message.chat.id, f"For what?", reply_markup=types.ReplyKeyboardRemove())
        bot.register_next_step_handler(message, expense_handler3)
    except Exception:
        print(traceback.format_exc())
        new_request(message, error_msg)


def expense_handler3(message):
    if not set_current_id(message):
        return
    try:
        _, sender_name, req_dt = get_message_md(message, temp_data[message.chat.id]['md'])
        price = temp_data[message.chat.id]['expense']
        price_str = temp_data[message.chat.id]['expense_str']
        reason = message.text
        
        current_week = (req_dt - timedelta(days=req_dt.weekday())).date()
        expenses = temp_data[message.chat.id]['md']['functions']['get_expenses']()
        index = (max([x['index'] for x in expenses['entries']]) + 1) if len(expenses['entries']) > 0 else 0
        expenses['entries'].append({'index': index, 'name': sender_name, 'price': price, 'reason': reason,
                                    'year': current_week.year, 'month': current_week.month, 'day': current_week.day})
        temp_data[message.chat.id]['md']['functions']['save_expenses'](expenses)
        reason_str = f' "{reason}"' if reason != '' else ''
        new_request(message, f'✅ Your expense{reason_str} for {price_str} has been recorded.')
    except Exception:
        print(traceback.format_exc())
        new_request(message, error_msg)


def ping_handler1(message):
    if not set_current_id(message):
        return
    new_request(message, f'✅ I am here bro! Chat-id: {message.from_user.id}')


def expenses_handler1(message):
    if not set_current_id(message):
        return
    try:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
        markup.row("NO", "YES")
        bot.send_message(message.chat.id, f"Do you want to continue from last index?", reply_markup=markup)
        bot.register_next_step_handler(message, expenses_handler2)
    except Exception:
        print(traceback.format_exc())
        new_request(message, error_msg)


def expenses_handler2(message):
    if not set_current_id(message):
        return
    try:
        if message.text == 'YES':
            temp_data[message.chat.id] = {'continue': True}
            expenses_handler3(message)
        elif message.text == 'NO':
            temp_data[message.chat.id] = {'continue': False}
            bot.send_message(message.chat.id, f"From which index you want to display the expenses?", reply_markup=types.ReplyKeyboardRemove())
            bot.register_next_step_handler(message, expenses_handler3)
        else:
            new_request(message, "❌ I really don't get it..")
            return
    except Exception:
        print(traceback.format_exc())
        new_request(message, error_msg)

def expenses_handler3(message):
    if not set_current_id(message):
        return
    try:
        in_index = None
        md = get_general_metadata()
        sender_activity, sender_name, req_dt = get_message_md(message, md)
        last_idx_path = os.path.join(os.path.dirname(__file__), 'last_idx_reads.json')
        if not os.path.exists(last_idx_path):
            with open(last_idx_path, 'w') as file:
                json.dump({}, file)
        expenses = md['functions']['get_expenses']()
        max_index = max([x['index'] for x in expenses['entries']]) if len(expenses['entries']) > 0 else -1
        with open(last_idx_path, 'r') as file:
            last_idx = {**{sender_name: -1}, **json.load(file)}
        if not temp_data[message.chat.id]['continue']:
            try:
                in_index = int(message.text)
                assert in_index >= 0
                in_index -= 1
            except Exception:
                new_request(message, "❌ Wrong index.")
                return
        else:
            if sender_name in last_idx:
                in_index = last_idx[sender_name]
            else:
                in_index = -1
        
        if in_index >= max_index:
            new_request(message, "❌ No updates here!")
            return

        expenses_list = [
            [e['index'], e['name'], e['price'], e['reason'], date_(day=e['day'], month=e['month'], year=e['year']).strftime("%d/%m/%y")]
            for e in expenses['entries'] if e['index'] > in_index
        ]
        expenses_df = pd.DataFrame(data=expenses_list, columns=['Index', 'Name', 'Price', 'Reason', 'Date'])

        totals_by_name = expenses_df.groupby("Name")["Price"].sum().reset_index()
        totals_by_name.columns = ["Name", "Total Price"]
        excel_path = os.path.join(os.path.dirname(__file__), "expenses.xlsx")

        with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
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

        new_request(message, f'All the expenses from index {in_index+1}.', document=excel_path)
        with open(last_idx_path, 'w') as file:
            last_idx[sender_name] = max_index
            json.dump(last_idx, file)
    except Exception:
        print(traceback.format_exc())
        new_request(message, error_msg)


class Action:
    def __init__(self, id, label, handle_request_chain, only_to=None):
        self.id = id
        self.label = label
        self.handle_request_chain = handle_request_chain
        self.only_to = only_to
    
    def start_chain(self, message):
        data = {'action': self}
        message.data = data
        self.handle_request_chain(message)

    def get_label(self, target_id):
        if self.only_to is None or (self.only_to is not None and target_id in self.only_to):
            return self.label

bot = telebot.TeleBot(LEO_TOKEN)
actions = {
    'blame': Action('blame', '💢 BLAME', blame_handler1),
    'warn': Action('warn', '⚠️ WARN', blame_handler1),
    'praise': Action('praise', '👏 PRAISE', blame_handler1),
    'swap': Action('swap', '🔄 SWAP', swap_handler1),
    'vacations': Action('vacations', '🌴 VACATIONS', vacations_handler1),
    'book': Action('book', '🏖 BOOK VACATION', vacation_handler1),
    'expense': Action('expense', '💰 EXPENSE', expense_handler1),
    'ping': Action('ping', '🛎 PING', ping_handler1, only_to=[807946519]),
    'finance': Action('finance', '📊 Finance', expenses_handler1, only_to=[807946519, 133279076]),
    'break': Action('break', BREAK_TOKEN, break_handler),
}

def get_welcome_markup(target_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
    rows = []
    rows.append(['blame', 'warn', 'praise'])
    rows.append(['swap', 'vacations'])
    rows.append(['book', 'expense'])
    rows.append(['ping', 'finance', 'break'])
    rows = [[actions[x].get_label(target_id) for x in row if x is not None] for row in rows]
    rows = [[x for x in row if x is not None] for row in rows]
    rows = [row for row in rows if len(row) > 0]
    for r in rows:
        markup.row(*r)
    return markup


@bot.message_handler(func=lambda m: True)
def send_welcome(message):
    if message.chat.id not in temp_data:
        temp_data[message.chat.id] = {}
    if message.text == BREAK_TOKEN:
        if not set_current_id(message):
            return
    bot.send_message(message.chat.id, "How can I be your hero today?", reply_markup=get_welcome_markup(message.chat.id))
    bot.register_next_step_handler(message, execute_request)


def set_current_id(message):
    if message.chat.id not in temp_data:
        temp_data[message.chat.id] = {}
    if 'current_id' in temp_data[message.chat.id] and message.id < temp_data[message.chat.id]['current_id']:
        return False
    temp_data[message.chat.id]['current_id'] = message.id
    return True


@bot.callback_query_handler(func=DetailedTelegramCalendar.func())
def cal(c):
    if c.message.text == BREAK_TOKEN:
        return
    if not set_current_id(c.message):
        return
    result, key, step = DetailedTelegramCalendar().process(c.data)
    if not result and key:
        bot.edit_message_text(f"{temp_data[c.message.chat.id]['calendar_title']} Select {LSTEP[step]}",
                              c.message.chat.id,
                              c.message.message_id,
                              reply_markup=key)
    elif result:
        temp_data[c.message.chat.id]['calendar_result'] = result
        temp_data[c.message.chat.id]['calendar_on_result'](c.message)


def new_request(message, text, target_id=None, document=None):
    target_id = message.chat.id if target_id is None else target_id
    if document is not None:
        with open(document, 'rb') as document_:
            bot.send_document(target_id, document_, caption=text, reply_markup=get_welcome_markup(target_id))
    else:
        if not set_current_id(message):
            return
        bot.send_message(target_id, text, reply_markup=get_welcome_markup(target_id))
    bot.register_next_step_handler(message, execute_request)


def execute_request(message):
    handled = False
    for action in actions.values():
        if message.text == action.label:
            action.start_chain(message)
            handled = True
            break
    if not handled:
        bot.send_message(message.chat.id, "❌ Did you just speak in Martian? Say again.", reply_markup=get_welcome_markup(message.chat.id))
        bot.register_next_step_handler(message, execute_request)


def reload_module(module_name):
    if module_name in sys.modules:
        module = importlib.reload(sys.modules[module_name])
    else:
        module = importlib.import_module(module_name)
    return module


def get_blame(name, now, hist_df, logs):
    filtered_row = hist_df[hist_df['Week'] == now]
    value = [list(v.values())[0] for k, v in filtered_row.to_dict().items() if k == name]
    if len(value) == 0:
        return [], None
    activity = value[0]
    blames = [k for k, v in logs.items() if len([j for j in v if (j['date'] == now and j['blame'] == activity)]) > 0]
    return blames, activity


def set_announcement(updated=False):
    try:
        subprocess.run(f'cd {WG_project_path} && git pull', shell=True, capture_output=True, text=True)
        with open(BLAME_LOGS_FILEPATH, 'r') as file:
            logs = json.load(file)
        md = get_general_metadata()

        emoticons = md['emoticons']
        now = datetime.now()
        now = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        blame_first_date = (now - timedelta(days=14)).date()
        blame_last_date = (now - timedelta(days=7)).date()
        hist_df = md['functions']['get_history']()
        for e in md['wg_props']:
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
        text, week_schedule = md['functions']['generate_plan']()
        text = intro + text
        if not updated:
            text += "\n\nNote: If you want to swap your task with someone else's task, use the SWAP command."
            text += "\nYou can submit an anonymous complaint for one or more tasks of the previous week by sending a BLAME."
            text += "\nBefore blaming someone, please wait until Wednesday evening so that the person has time to recover their delayed duty."
            text += "\nIf a person receives at least 2 blames, they will need to recover the task in the future ☠️."
            text += "\nAlternatively, you can send a warning ⚠️ to that person by sending a WARN."
            text += "\nYou can also send a message of appreciation 🌟 by sending a PRAISE as well."
            text += "\nIf you need vacation for a week, you can send book it though BOOK VACATION."
            text += "\nWhenever you have a WG expense 💰, use EXPENSE and specify price/reason for it."

        subprocess.run(f'cd {WG_project_path} && git add . && git commit -m "auto_update" && git push', shell=True, capture_output=True, text=True)
        if not debug_flag:
            bot.send_document(LEO_GROUP_ID, os.path.join(WG_project_path, 'cleaning_plan_leo6.xlsx'), caption=text)
        print('Msg sent to LEO6:', text)

        with open(os.path.join(os.path.dirname(__file__), 'announcements.txt'), 'a+') as file:
            file.write(datetime.now().strftime("%Y-%m-%d-%H-%M-%S") + '\n')
        
        for e in md['wg_props']:
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
            if telegram_id is not None:
                print('Msg sent:', string)
                if name == 'Claudio' or not debug_flag:
                    bot.send_message(telegram_id, string, parse_mode="HTML")
    except Exception as e:
        print(e)
        print(traceback.format_exc())


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


def spawn_monitoring(signal={'kill': False}):
    global bot, l_signal
    l_signal = signal
    monitor_thread = threading.Thread(target=monitor_kill, args=(bot, signal))
    monitor_thread.start()
    bot.enable_save_next_step_handlers(delay=2)
    bot.load_next_step_handlers()
    bot.infinity_polling()
    signal['kill'] = True
    print('BOT STOPPED')


def monitor_kill(bot, signal):
    while not signal['kill']:
        if 'set_announcement' in signal:
            set_announcement(**signal['set_announcement'])
            del signal['set_announcement']
        time.sleep(0.5)
    bot.stop_polling()


def update(last_announcement=None, id_last_announcement=None, forced=False, updated=False):
    global l_signal
    now = datetime.now()
    announce_at = 8  # hour of update
    masked_now = now - timedelta(hours=(announce_at))
    if forced or get_week_number(masked_now) != id_last_announcement:
        if forced or masked_now > last_announcement:
            print('ANNOUNCEMENTS', now)
            l_signal['set_announcement'] = {'updated': updated}
            last_announcement = now
            id_last_announcement = get_week_number(now)
    return last_announcement, id_last_announcement


if __name__ == '__main__':
    spawn_monitoring()
