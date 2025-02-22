import subprocess
import time
from BAC_logic import *
import json

initialize_proj()

with open(f'{wg_folder}/vacations.json', 'r') as file:
    vac_entries = json.load(file)['entries']

with open(f'{wg_folder}/swaps.json', 'r') as file:
    swap_entries = json.load(file)['entries']

vacations = Vacations(entries=[Entry(names=e['names'],
                                     in_date=datetime.date(year=e['year'], month=e['month'], day=e['day']),
                                     n_weeks=e['n_weeks']) for e in vac_entries])

swaps = Swaps(entries=[Entry(names=[e['name1'], e['name2']],
                             in_date=datetime.date(year=e['year'], month=e['month'], day=e['day']),
                             ) for e in swap_entries])

dt = datetime.datetime.now() - datetime.timedelta(days=0)
date_now = (dt - datetime.timedelta(days=dt.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
wg_members, text, week_schedule = start_bac(vacations, swaps, save=False, dt=date_now)

print(week_schedule)

# print()
# if wg_members is not None:
#     for m in wg_members.members:
#         print(f'{m.name}: {m.p_activities} debit: {m.debit}  - spread: {m.spread}')

