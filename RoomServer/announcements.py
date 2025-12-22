import importlib
import os
import sys
import traceback
import json
import threading
import time
from datetime import datetime, timedelta
from utils import pull, push
from wg import bac, bac_utils
from announcements_functions import *
from utils import BLAME_LOGS_FILEPATH, ANNOUNCEMENT_FILEPATH, MAIN_FOLDER_PATH, MSG_HISTORY_PATH


debug_flag = True


def reload_module(module_name):
    if module_name in sys.modules:
        module = importlib.reload(sys.modules[module_name])
    else:
        module = importlib.import_module(module_name)
    return module


def get_blame(name, now, hist_df, logs):
    filtered_row = hist_df[hist_df['Week'] == now]
    values = [list(v.values()) for k, v in filtered_row.to_dict().items() if k == name]
    values = [x[0] for x in values if len(x) > 0]
    if len(values) == 0:
        return [], None
    activity = values[0]
    blames = [k for k, v in logs.items() if len([j for j in v if (j['date'] == now and j['blame'] == activity)]) > 0]
    return blames, activity


def set_announcement(updated=False):
    global bh
    try:
        if not pull(MAIN_FOLDER_PATH, bh.signal):
            return
        with open(BLAME_LOGS_FILEPATH, 'r') as file:
            logs = json.load(file)
        md = get_general_metadata()

        emoticons = md['emoticons']
        now = get_current_time()
        now = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        blame_first_date = (now - timedelta(days=14)).date()
        blame_last_date = (now - timedelta(days=7)).date()
        hist_df = md['functions']['get_history']()
        for e in md['wg_props']:
            name = e['name']
            date = str(blame_first_date)
            blames, blamed_activity = get_blame(name, date, hist_df, logs)
            if len(blames) >= 2:
                blames_json = bac.get_blames()
                blames_json['entries'].append({'name': name, 'date': date})
                bac.save_blames(blames_json)

        intro = '<b>🔄 PLAN UPDATED DURING THIS WEEK</b>\n' if updated else ''
        text, week_schedule = bac.generate_plan()
        text = intro + text
        if not updated:
            text += "\n\nNote: If you want to swap your task with someone else's task, use the SWAP command."
            text += "\nYou can submit an anonymous complaint for one or more tasks of the previous week by sending a BLAME."
            text += "\nIf a person receives at least 2 blames, they will need to recover the task in the future ☠️."
            text += "\nYou can also send a message of appreciation 🌟 by sending a PRAISE as well."
            text += "\nIf you need vacation for a week, you can send book it though BOOK VACATION."
            text += "\nWhenever you have a WG expense 💰, use EXPENSE and specify price/reason for it."

        document_ = bac_utils.get_plan_document()
        
        for e in md['wg_props']:
            name = e['name']
            blames, blamed_activity = get_blame(name, str(blame_first_date), hist_df, logs)
            telegram_id = e['telegram_id']
            string = f'Hey {name}, this is the schedule for the next weeks, waiting for you! 🤩\n'
            string += 'Keep in mind that this is just a preview on your next activities.. things may change!\n\n'
            for week_n, week_tasks in enumerate(week_schedule):
                week_now = (now + timedelta(days=(week_n * 7))).date().strftime("%d/%m")
                week_plus_1 = (now + timedelta(days=((week_n + 1) * 7))).date().strftime("%d/%m")
                pre = 'RANGE: ACT\n'
                # if week_n == 0:
                #     pre = 'This week (RANGE): ACT\n'
                # elif week_n == 1:
                #     pre = 'Next week (RANGE): ACT\n'
                activity = week_tasks[name]
                marker = "🟨" if week_n == 0 else "📅"
                string += pre.replace('RANGE', f'{marker} {week_now} - {week_plus_1}').replace('ACT', f' <b>{activity}</b> {emoticons[activity][:2]}')
            if blamed_activity != 'Vacation' and not updated:
                if len(blames) == 0:
                    string += f'\n👍 Congratulations, you have no complaints for the week ' +\
                              f'{blame_first_date.strftime("%d/%m")} - {blame_last_date.strftime("%d/%m")}!'
                else:
                    blamed_activity = f' ({blamed_activity})' if blamed_activity is not None else ''
                    string += f'\n⚠️ You got {len(blames)} complaint{"s" if len(blames) > 1 else ""} in the week {blame_first_date}-{blame_last_date}{blamed_activity}.'
                    if len(blames) >= 2:
                        string += f'\n☠️ Unfortunately you will have to compensate in the next weeks with more tasks.'
            if telegram_id is not None:
                if name == 'Claudio' or not debug_flag:
                    try:
                        bh.bot.send_document(telegram_id, document_, caption=text + "\n\n" + string, parse_mode="HTML")
                        # bh.send_msg(telegram_id, string, parse_mode="HTML")
                        print('Msg sent:', string)
                    except Exception as e:
                        print(e)
                        print(traceback.format_exc())

        with open(ANNOUNCEMENT_FILEPATH, 'a+') as file:
            file.write(get_current_time().strftime("%Y-%m-%d-%H-%M-%S") + '\n')
        # print('Msg sent to LEO6:', text)

        push(MAIN_FOLDER_PATH, bh.signal)
    except Exception as e:
        print(e)
        print(traceback.format_exc())


def get_week_number(date):
    return date.isocalendar()[1], date.year


def get_date_from_week_id(week_id_):
    d = f"{week_id_[1]}-W{week_id_[0]}"
    return datetime.strptime(d + '-1', "%Y-W%W-%w").date()


def get_last_announcement():
    global bh
    pull(MAIN_FOLDER_PATH, bh.signal)
    last_announcement = None
    try:
        with open(ANNOUNCEMENT_FILEPATH, 'r') as file:
            last_announcement = datetime.strptime(file.read().split('\n')[-2], "%Y-%m-%d-%H-%M-%S")
    except:
        pass
    if last_announcement is None:
        last_announcement = datetime.strptime("2000-01-01-00-00-00", "%Y-%m-%d-%H-%M-%S")
    return last_announcement, get_week_number(last_announcement)


def spawn_monitoring(signal_):
    global bh, bot_history
    bac.initialize_repo()
    print('Bot is ready.')
    if os.path.exists(MSG_HISTORY_PATH):
        with open(MSG_HISTORY_PATH, 'r') as file:
            bot_history = json.load(file)
    else:
        bot_history = {}
    bh.signal = signal_
    monitor_thread = threading.Thread(target=monitor, args=(bh, ))
    monitor_thread.start()
    bh.bot.enable_save_next_step_handlers(delay=2)
    bh.bot.load_next_step_handlers()
    bh.bot.infinity_polling()
    print('Bot killed.')


def monitor(bh):
    last_announcement, id_last_announcement = get_last_announcement()
    index = 0
    while not bh.signal['kill']:
        if 'set_announcement' in bh.signal:
            set_announcement(**bh.signal['set_announcement'])
            del bh.signal['set_announcement']
        index += 1
        if index == 60:
            save_history()
            index = 0
        try:
            last_announcement, id_last_announcement = update(last_announcement, id_last_announcement)
            time.sleep(1)
        except Exception:
            import traceback
            print(traceback.format_exc())
        time.sleep(0.5)
    time.sleep(0.5)
    save_history()
    bh.bot.stop_polling()


def update(last_announcement=None, id_last_announcement=None, forced=False, updated=False):
    global bh
    now = get_current_time()
    announce_at = 8  # hour of update
    masked_now = now - timedelta(hours=(announce_at))
    if forced or get_week_number(masked_now) != id_last_announcement:
        if forced or masked_now > last_announcement:
            print('ANNOUNCEMENTS', now)
            bh.signal['set_announcement'] = {'updated': updated}
            last_announcement = now
            id_last_announcement = get_week_number(now)
    return last_announcement, id_last_announcement


def save_history():
    with open(MSG_HISTORY_PATH, 'w') as file:
        json.dump(bot_history, file, indent=2)


if __name__ == '__main__':
    spawn_monitoring({'kill': False})
