import subprocess
from cleaning_plan import *
import json

subprocess.run(f'cd {os.path.dirname(__file__)} && git pull'.split(), shell=True, capture_output=True, text=True)

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
wg_members, text, week_schedule = start_bac(vacations, swaps, save=False)

print()
if wg_members is not None:
    for m in wg_members.members:
        print(f'{m.name}: {m.p_activities} debit: {m.debit}  - spread: {m.spread}')

