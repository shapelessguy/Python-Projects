import telegram
import asyncio
import os
import sys

WG_project_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'WG')
sys.path.append(WG_project_path)
from execute_logic import generate_plan
from BAC_logic import WgMembers, WgProps
from utils import LEO_TOKEN, CLAUDIO_ID

plan = generate_plan()
bot = telegram.Bot(token=LEO_TOKEN)


async def send(chat_id, token, msg, document=None):
    # bot = telegram.Bot(token=token)
    if document is None:
        await bot.send_message(chat_id=chat_id, text=msg)
    elif document is not None:
        await bot.send_document(chat_id=chat_id, document=document, caption=msg)
    print(f"Message '{msg}' sent.")


# asyncio.run(send(chat_id=CLAUDIO_ID, token=LEO_TOKEN, msg='HEEEY'))
asyncio.run(send(chat_id=CLAUDIO_ID, token=LEO_TOKEN, msg=plan, document='cleaning_plan_leo6.xlsx'))
