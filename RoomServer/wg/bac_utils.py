import os
import sys
import pandas
import json
import io
import datetime
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from wg.variables import members, nominal_activities


DATA_PATH = os.path.join(os.path.dirname(__file__), 'dataNew')

PLAN_FILEPATH = os.path.join(DATA_PATH, 'cleaning_plan_leo6.xlsx')
HISTORY_FILEPATH = os.path.join(DATA_PATH, 'history.csv')
VACATIONS_FILEPATH = os.path.join(DATA_PATH, 'vacations.json')
SWAPS_FILEPATH = os.path.join(DATA_PATH, 'swaps.json')
EXPENSES_FILEPATH = os.path.join(DATA_PATH, 'expenses.json')
BLAMES_FILEPATH = os.path.join(DATA_PATH, 'blames.json')


def get_history():
    if os.path.exists(HISTORY_FILEPATH):
        hist_df = pandas.read_csv(HISTORY_FILEPATH)
        hist_df['Week'] = pandas.to_datetime(hist_df['Week'])
        column_order = ["Week"] + sorted([col for col in hist_df.columns if col != "Week"])
        hist_df = hist_df[column_order]
    else:
        hist_df = pandas.DataFrame(columns=["Week"] + [x['name'] for x in members])
        save_history(hist_df)
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
    else:
        save_vacations(vacations)
    return vacations


def get_swaps():
    swaps = {'entries': []}
    if os.path.exists(SWAPS_FILEPATH):
        with open(SWAPS_FILEPATH, 'r') as file:
            swaps = json.load(file)
    else:
        save_swaps(swaps)
    return swaps


def get_expenses():
    expenses = {'entries': []}
    if os.path.exists(EXPENSES_FILEPATH):
        with open(EXPENSES_FILEPATH, 'r') as file:
            expenses = json.load(file)
    else:
        save_expenses(expenses)
    return expenses


def get_blames():
    blames = {'entries': []}
    if os.path.exists(BLAMES_FILEPATH):
        with open(BLAMES_FILEPATH, 'r') as file:
            blames = json.load(file)
    return blames


def save_history(df):
    try:
        df.to_csv(HISTORY_FILEPATH, index=False)
    except Exception as error:
        print(error)


def save_vacations(vacations):
    with open(VACATIONS_FILEPATH, 'w') as file:
        json.dump(vacations, file, indent=4)


def save_swaps(swaps):
    with open(SWAPS_FILEPATH, 'w') as file:
        json.dump(swaps, file, indent=4)


def save_expenses(expenses):
    with open(EXPENSES_FILEPATH, 'w') as file:
        json.dump(expenses, file, indent=4)


def save_blames(blames):
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


class Date:
    def __init__(self):
        self.timestamp = datetime.datetime.now()
    
    def get_ts(self):
        return self.timestamp
    
    def get_date(self):
        return self.timestamp.date()
    
    def get_monday(self, add_weeks: int=0, to_timestamp: bool=False):
        monday = self.timestamp.date() - datetime.timedelta(days=self.timestamp.date().weekday()) + datetime.timedelta(days=7 * add_weeks)
        if to_timestamp:
            monday = datetime.datetime.combine(monday, datetime.datetime.min.time())
        return monday


class Activity:
    def __init__(self, name, emoticons, description=[]):
        self.name = name
        self.emoticons = emoticons
        self.description = description


class Activities:
    def __init__(self):
        for idx, activity_data in enumerate(nominal_activities, start=1):
            name = activity_data["name"]
            emoji = activity_data["emoji"]
            description = activity_data.get("description", [])
            setattr(self, f"area{idx}", Activity(name, emoji, description))
        self.vacation = Activity("Vacation", "🗽🗼🏜️🏝️")
        self.blame = Activity("Blame", "😑😲😠🤬")
        self.anarchy = Activity("Anarchy", "😈😈😈😈")

    def get_regular(self):
        return [
            value for k, value in self.__dict__.items() if isinstance(value, Activity) and 'area' in k
        ]

    def get_regular_with_vacation(self):
        return self.get_regular() + [self.vacation]

    def get_vacation(self):
        return self.vacation

    def get_blame(self):
        return self.blame

    def get_anarchy(self):
        return self.anarchy

    def get_all(self):
        return self.get_regular() + [self.vacation, self.blame, self.anarchy]
    
    def get_roles_df(self):
        dict_ = {a.name: [x for x in a.description] + [''] * (50 - len(a.description)) for a in self.get_regular() if a.description}
        max_len = max([sum([(1 if line != '' else 0) for line in dict_[area]]) for area in dict_])
        dict_ = {a: dict_[a][:max_len] for a in dict_}
        return pandas.DataFrame.from_dict(dict_)
    
    def get_activity_by_name(self, name):
        for a in self.get_all():
            if a.name == name:
                return a
        print(f"Error: Name {name} not found in activities names.")
        return None
