import subprocess
import time
from cleaning_plan import *
import json


def generate_plan():
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
        start_bac(vacations, swaps, save=False)
    except Exception as ex:
        print(f'Exception:\n{ex}')
        pyperclip.copy(f'Exception:\n{ex}')


if __name__ == '__main__':
    generate_plan()
