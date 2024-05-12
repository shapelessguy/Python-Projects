import telegram
import asyncio
import os
import sys

WG_project_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'WG')
sys.path.append(WG_project_path)
from cleaning_plan_sequence import generate_plan
from cleaning_plan import WgMembers, WgProps

plan = generate_plan()
leo_token = '6599624331:AAETjn6YXAXVkg4-IV1I_1ip6zchZdmNbUI'
claudio_id = 807946519
mara_id = 133279076
leo_group_id = -4225824414
dummy_channel_id = -1002037672769
bot = telegram.Bot(token=leo_token)


async def send(chat_id, token, msg, document=None):
    # bot = telegram.Bot(token=token)
    if document is None:
        await bot.send_message(chat_id=chat_id, text=msg)
    elif document is not None:
        await bot.send_document(chat_id=chat_id, document=document, caption=msg)
    print(f"Message '{msg}' sent.")


# asyncio.run(send(chat_id=claudio_id, token=leo_token, msg='HEEEY'))
asyncio.run(send(chat_id=claudio_id, token=leo_token, msg=plan, document='cleaning_plan_leo6.xlsx'))
