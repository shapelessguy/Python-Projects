import os
import pandas
import json
import io


WG_PATH = os.path.dirname(__file__)
DATA_PATH = os.path.join(WG_PATH, 'data')

PLAN_FILEPATH = os.path.join(DATA_PATH, 'cleaning_plan_leo6.xlsx')
HISTORY_FILEPATH = os.path.join(DATA_PATH, 'history.csv')
VACATIONS_FILEPATH = os.path.join(DATA_PATH, 'vacations.json')
SWAPS_FILEPATH = os.path.join(DATA_PATH, 'swaps.json')
EXPENSES_FILEPATH = os.path.join(DATA_PATH, 'expenses.json')
BLAMES_FILEPATH = os.path.join(DATA_PATH, 'blames.json')


def get_history():
    if os.path.exists(HISTORY_FILEPATH):
        try:
            hist_df = pandas.read_csv(HISTORY_FILEPATH)
            hist_df['Week'] = pandas.to_datetime(hist_df['Week'])
            column_order = ["Week"] + sorted([col for col in hist_df.columns if col != "Week"])
            hist_df = hist_df[column_order]
        except pandas.errors.EmptyDataError:
            return None
    return hist_df


def get_plan():
    if os.path.exists(PLAN_FILEPATH):
        return pandas.read_excel(PLAN_FILEPATH)
    return None


def get_plan_document():
    document = None
    if os.path.exists(PLAN_FILEPATH):
        with open(PLAN_FILEPATH, 'rb') as document_:
            document = io.BytesIO(document_.read())
            document.seek(0)
            document.name = "Calendar.xlsx"
    return document


def get_vacations():
    vacations = {'entries': []}
    if os.path.exists(VACATIONS_FILEPATH):
        with open(VACATIONS_FILEPATH, 'r') as file:
            vacations = json.load(file)
    return vacations


def get_swaps():
    swaps = {'entries': []}
    if os.path.exists(SWAPS_FILEPATH):
        with open(SWAPS_FILEPATH, 'r') as file:
            swaps = json.load(file)
    return swaps


def get_expenses():
    expenses = {'entries': []}
    if os.path.exists(EXPENSES_FILEPATH):
        with open(EXPENSES_FILEPATH, 'r') as file:
            expenses = json.load(file)
    return expenses


def get_blames():
    blames = {'entries': []}
    if os.path.exists(BLAMES_FILEPATH):
        with open(BLAMES_FILEPATH, 'r') as file:
            blames = json.load(file)
    return blames


def save_vacations(vacations):
    if os.path.exists(VACATIONS_FILEPATH):
        with open(VACATIONS_FILEPATH, 'w') as file:
            json.dump(vacations, file, indent=4)


def save_swaps(swaps):
    if os.path.exists(SWAPS_FILEPATH):
        with open(SWAPS_FILEPATH, 'w') as file:
            json.dump(swaps, file, indent=4)


def save_expenses(expenses):
    if os.path.exists(EXPENSES_FILEPATH):
        with open(EXPENSES_FILEPATH, 'w') as file:
            json.dump(expenses, file, indent=4)


def save_blames(blames):
    if os.path.exists(BLAMES_FILEPATH):
        with open(BLAMES_FILEPATH, 'w') as file:
            json.dump(blames, file, indent=4)


def expenses_to_xlsx(expenses_df):
    expenses_df.to_excel(EXPENSES_FILEPATH, index=False)
    return EXPENSES_FILEPATH


class bcolors:
    """Text colors for terminal visibility."""

    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    ORANGE = "\033[38;5;208m"
    RED = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
