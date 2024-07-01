import subprocess
import time
from BAC_logic import *
import json
import traceback


def generate_plan():
    text = 'Error'
    try:
        r = subprocess.run(f'cd {os.path.dirname(__file__)} && git pull'.split(), shell=True, capture_output=True, text=True)
        print(r.stdout)
        print(r.stderr)
        time.sleep(1)
        
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
        wg_members, text, week_schedule = start_bac(vacations, swaps, save=True)
    except Exception as ex:
        print(f'Exception:\n{ex}', traceback.format_exc())
        pyperclip.copy(f'Exception:\n{ex}')
    return text, week_schedule


if __name__ == '__main__':
    generate_plan()
