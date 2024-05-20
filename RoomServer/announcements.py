import importlib
import os
import subprocess
import sys
import datetime
import telegram
import asyncio


main_folder = os.path.dirname(os.path.dirname(__file__))
RoomServer_project_path = os.path.dirname(__file__)
WG_project_path = os.path.join(main_folder, 'WG')
sys.path.append(WG_project_path)


def get_week_number(date):
    return date.isocalendar()[1], date.year


def get_date_from_week_id(week_id_):
    d = f"{week_id_[1]}-W{week_id_[0]}"
    return datetime.datetime.strptime(d + '-1', "%Y-W%W-%w").date()


def get_last_announcement():
    last_announcement = None
    try:
        with open(os.path.join(os.path.dirname(__file__), 'announcements.txt'), 'r') as file:
            last_announcement = datetime.datetime.strptime(file.read().split('\n')[-2], "%Y-%m-%d-%H-%M-%S")
    except:
        pass
    if last_announcement is None:
        last_announcement = datetime.datetime.strptime("2000-01-01-00-00-00", "%Y-%m-%d-%H-%M-%S")
    return last_announcement, get_week_number(last_announcement)


async def send(chat_id, token, msg, document=None):
    bot = telegram.Bot(token=token)
    if document is None:
        await bot.send_message(chat_id=chat_id, text=msg, parse_mode="HTML")
    elif document is not None:
        await bot.send_document(chat_id=chat_id, document=document, caption=msg)
    print(f"Message '{msg}' sent.")


def reload_module(module_name):
    if module_name in sys.modules:
        module = importlib.reload(sys.modules[module_name])
    else:
        module = importlib.import_module(module_name)
    return module


def set_announcement(last_announcement):
    try:
        subprocess.run(f'cd {WG_project_path} && git pull'.split(), shell=True, capture_output=True, text=True)
        cleaning_plan_sequence = reload_module('cleaning_plan_sequence')
        cleaning_plan = reload_module('cleaning_plan_sequence')
        generate_plan = cleaning_plan_sequence.generate_plan
        WgMembers = cleaning_plan.WgMembers
        WgProps = cleaning_plan.WgProps
        emoticons = cleaning_plan.emoticons
        print(emoticons)

        text, week_schedule = generate_plan()
        subprocess.run(f'cd {WG_project_path} && git add . && git commit -m "auto_update" && git push'.split(), shell=True, capture_output=True, text=True)
        leo_token = '6599624331:AAETjn6YXAXVkg4-IV1I_1ip6zchZdmNbUI'
        leo_group_id = -4225824414
        dummy_channel_id = -1002037672769
        asyncio.run(send(chat_id=leo_group_id, token=leo_token, msg=text, document=os.path.join(WG_project_path, 'cleaning_plan_leo6.xlsx')))

        with open(os.path.join(os.path.dirname(__file__), 'announcements.txt'), 'a+') as file:
            file.write(last_announcement.strftime("%Y-%m-%d-%H-%M-%S") + '\n')

        wg_members = {k: v for k, v in WgMembers.__dict__.items() if not k.startswith('__')}
        wg_props = [{'name': wg_members[k], **v, } for k, v in WgProps.__dict__.items() if not k.startswith('__')]
        now = datetime.datetime.combine(get_date_from_week_id(get_week_number(datetime.datetime.now().date())), datetime.datetime.min.time())
        for e in wg_props:
            name = e['name']
            telegram_id = e['telegram_id']
            string = f'Hello {name}, this is the schedule for the next weeks, waiting for you!\n'
            for week_n in week_schedule:
                week_now = (now + datetime.timedelta(days=(week_n * 7))).date().strftime("%d-%m-%y")
                week_plus_1 = (now + datetime.timedelta(days=((week_n + 1) * 7))).date().strftime("%d-%m-%y")
                pre = 'Week RANGE: ACT\n'
                if week_n == 0:
                    pre = 'This week (RANGE): ACT\n'
                elif week_n == 1:
                    pre = 'Next week (RANGE): ACT\n'
                activity = week_schedule[week_n][name]
                string += pre.replace('RANGE', f'{week_now} - {week_plus_1}').replace('ACT', f' <b>{activity}</b> {emoticons[activity]}')
            if telegram_id is not None:
                asyncio.run(send(chat_id=telegram_id, token=leo_token, msg=string))
    except Exception as e:
        print(e)


def update(now, last_announcement, id_last_announcement, forced=False):
    announce_at = 8  # hour of update
    masked_now = now - datetime.timedelta(hours=(announce_at))
    if get_week_number(masked_now) != id_last_announcement or forced:
        if masked_now > last_announcement or forced:
            print('ANNOUNCEMENTS', now)
            set_announcement(now)
            last_announcement = now
            id_last_announcement = get_week_number(now)
    return last_announcement, id_last_announcement
