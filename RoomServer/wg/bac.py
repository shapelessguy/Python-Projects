import itertools
import os
import sys
import pandas
from pandas import DataFrame
sys.path.append(os.path.dirname(__file__))
from bac_utils import *
import datetime


class Activity:
    def __init__(self, name, emoticons, description=[]):
        self.name = name
        self.emoticons = emoticons
        self.description = description


class Activities:
    def __init__(self):
        self.area1 = Activity("Floor", "🧹🪣🫧", description=[
            "Hallway's floor",
            "Kitchen's floor",
            "Shoe rack"
        ])
        self.area2 = Activity("Kitchen", "🪑🚰🧴🔪", description=[
            "Surfaces + table",
            "Dish space + sink",
            "Oven + Microwave",
            "Stove"
        ])
        self.area3 = Activity("Bathrooms", "🛁🚽🧻🚾", description=[
            "Big bathroom's floor",
            "Big bathroom's steps",
            "Small bathroom's floor",
            "Shower bathtub + panel",
            "Sink",
            "Toilets",
            "Bath rag"
        ])
        self.area4 = Activity("Management", "💸🧺🍾", description=[
            "All trash + bins",
            "TO BUY list",
            "Bottles",
            "Wash laundry",
            "Toilet paper"
        ])
        self.vacation = Activity("Vacation", "💸🧺🍾")
        self.blame = Activity("Blame", "bleah")
        self.anarchy = Activity("Anarchy", "😈😈")

    def get_regular(self):
        return [self.area1, self.area2, self.area3, self.area4]

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


activities = Activities()


class WgMember:
    def __init__(self, name: str, telegram_id: int):
        self.name = name
        self.telegram_id = telegram_id
        self.activity_history = []
    
    def assign(self, activity: Activity):
        self.activity_history.append(activity)
    
    def get_repeat_idx(self, activity: Activity=None):
        """Get the distance (in terms of #tasks) of <activity> from the current time."""
        if activity is not None:
            repeat_idx = 0
            for a in self.activity_history[::-1]:
                if a in activities.get_regular():
                    repeat_idx += 1
                if activity == a:
                    break
            return repeat_idx
        else:
            activities_ = activities.get_regular()
            repetition_activities = {a: [] for a in activities_}
            repetition_idx = 0
            for a in self.activity_history[::-1]:
                if a in repetition_activities:
                    repetition_activities[a].append(repetition_idx)
                    repetition_idx += 1
            
            spread = {i: 0 for i in range(1, 10)}
            for a, v in repetition_activities.items():
                if len(v) > 1:
                    for x in [x2-x1 for x2, x1 in zip(v[1:], v[:-1])]:
                        if x in spread:
                            if x < 2:
                                print(self.name, a.name, x)
                            spread[x] += 1
            return list(spread.values())

    def get_debit(self, activity: Activity=None):
        """Get the total debt after assigning <activity> to the current member. The debt is the max #tasks of discrepancy between all types of tasks."""
        reg_activities = activities.get_regular()
        executed_activities = {a: 0 for a in reg_activities}
        for a in self.activity_history:
            if a in executed_activities:
                executed_activities[a] += 1
        if activity is not None and activity in reg_activities:
            executed_activities[activity] += 1
        return max(executed_activities.values()) - min(executed_activities.values())


class WgMembers:
    def __init__(self):
        self.m1 = WgMember("Jay", 1113618025)
        self.m2 = WgMember("Cesare", 6093567886)
        self.m3 = WgMember("Claudio", 807946519)
        self.m4 = WgMember("Natchaya", 6448393940)
        self.m5 = WgMember("Lea", 7129379343)
        self.m6 = WgMember("Mara", 133279076)
        self.initial_date = None
    
    def get_members(self):
        return [self.m1, self.m2, self.m3, self.m4, self.m5, self.m6]
    
    def get_member_by_name(self, name: str):
        for m in self.get_members():
            if m.name == name:
                return m
        print(f"Error: Name {name} not found in members names.")
        return None
    
    def calculate_fitness(self, state_option: dict):
        fitness = 0
        for m, activity in state_option.items():
            fitness += 100 / (m.get_repeat_idx(activity) + 0.1) + m.get_debit(activity)
        return fitness
    
    def swap(self, m1, m2):
        a1 = m1.activity_history.pop()
        a2 = m2.activity_history.pop()
        m1.assign(a2)
        m2.assign(a1)
    
    def to_df(self):
        n_weeks = len(self.get_members()[0].activity_history)
        dict_ = {"Week": [self.initial_date + datetime.timedelta(days=7 * i) for i in range(n_weeks)],
                 **{m.name: [a.name for a in m.activity_history] for m in self.get_members()}}
        df = pandas.DataFrame(dict_)
        column_order = ["Week"] + sorted([col for col in df.columns if col != "Week"])
        df = df[column_order]
        return df
    
    def __str__(self):
        df = self.to_df()
        return "Current WG state:\n" + df.to_string() + "\n"


def load_history():
    if not os.path.exists(HISTORY_FILEPATH):
        with open(HISTORY_FILEPATH, 'w') as file:
            file.write('')
    
    hist_df = get_history()
    blame = activities.get_blame().name
    if hist_df is not None:
        hist_df["Week"] = pandas.to_datetime(hist_df["Week"]).dt.date
        # Rewrite history df due to possible blames
        for entry in get_blames()['entries']:
            target_date = pandas.to_datetime(entry['date']).date()
            hist_df.loc[hist_df["Week"] == target_date, entry['name']] = blame
    return hist_df


def update_history(hist_df: pandas.DataFrame, wg_members: WgMembers, current_date: datetime.date):
    df = wg_members.to_df()
    df = pandas.concat([hist_df, df])
    df = df.drop_duplicates(subset=['Week'], keep='first')
    df = df.sort_values(by='Week')
    df = df[df["Week"] <= current_date]
    save_history(df)
    print("History updated")


def print_df(df, current_date):
    col = bcolors.CYAN
    df_str = str(df).split("\n")
    print()
    print(df_str[0])
    for line in df_str[1:]:
        if len(line.split()) < 2:
            continue
        date_str = line.split()[1]
        if date_str == str(current_date):
            col = bcolors.ORANGE
            print(f"{col}{line}{bcolors.ENDC}")
            col = bcolors.RED
        else:
            print(f"{col}{line}{bcolors.ENDC}")
    print()


def save_plan(wg_members: WgMembers, current_date: datetime.date, start_end_dates: list[datetime.date], previous_weeks=16):
    start_date = current_date - datetime.timedelta(days=current_date.weekday()) - datetime.timedelta(days=7 * previous_weeks)
    start_date = start_end_dates[0] if start_date < start_end_dates[0] else start_date
    end_date = start_end_dates[1]
    df = wg_members.to_df()
    reduced_df = df[(df["Week"] >= start_date) & (df["Week"] <= end_date)]
    dfs = {'Calendar': reduced_df, 'Roles': Activities().get_roles_df()}
    print_df(reduced_df, current_date)

    print(rf'Saving at {PLAN_FILEPATH}')
    writer = pandas.ExcelWriter(f'{PLAN_FILEPATH}', engine='xlsxwriter', date_format='dd.mm.yyyy')
    def align_center(x):
        return ['text-align: center' for _ in x]
    for name, dataframe in dfs.items():
        dataframe.style.apply(align_center, axis=0).to_excel(writer, name, index=False)
    writer.sheets['Calendar'].set_column(0, len(reduced_df.columns), 20)
    writer.sheets['Roles'].set_column(0, len(Activities().get_regular()) - 1, 30)
    highlightning = {
        Activities().get_vacation().name: writer.book.add_format({'bg_color': '#ffa500', 'font_color': '#FFFFFF'}),
        Activities().get_anarchy().name: writer.book.add_format({'bg_color': '#0b03fc', 'font_color': '#FFFFFF'}),
        Activities().get_blame().name: writer.book.add_format({'bg_color': '#fc0303', 'font_color': '#FFFFFF'}),
    }
    cf = [['A1:G1000', {'type': 'text', 'criteria': 'containing', 'value': k, 'format': v}] for k, v in highlightning.items()]
    writer.sheets['Calendar'].conditional_format('A1:A1000', {'type': 'date', 'criteria': 'equal', 'value': current_date,
                                                              'format': writer.book.add_format({'bg_color': '#03fc17'})})
    writer.sheets['Calendar'].conditional_format('A1:G1000', {'type': 'no_blanks', 'format': writer.book.add_format({'border': 1})})

    words = 'abcdefghijklmnopqrstuvwxyz'.upper()
    roles_height = max([len(a.description) for a in Activities().get_regular()]) + 1
    roles_lastw = words[len(Activities().get_regular()) - 1]

    writer.sheets['Roles'].conditional_format(f'A1:{roles_lastw}1', {'type': 'no_blanks', 'format': writer.book.add_format({'border': 1})})
    for type_ in ['no_blanks', 'blanks']:
        writer.sheets['Roles'].conditional_format(f'A1:{roles_lastw}{roles_height}',
                                                {'type': type_, 'format': writer.book.add_format({'bg_color': '#FFFFFF', 'left': 1, 'right': 1})})
    for c in cf:
        writer.sheets['Calendar'].conditional_format(*c)
    
    for i in range(len(reduced_df) + 1):
        writer.sheets['Calendar'].conditional_format(f'H{i+1}', {'type': 'blanks', 'format': writer.book.add_format({'left': 2})})
    for wi in range(len(reduced_df.columns)):
        writer.sheets['Calendar'].conditional_format(f'{words[wi]}{len(reduced_df)+2}', {'type': 'blanks', 'format': writer.book.add_format({'top': 2})})
    for i in range(roles_height):
        roles_lastw_ = words[len(Activities().get_regular())]
        writer.sheets['Roles'].conditional_format(f'{roles_lastw_}{i+1}', {'type': 'blanks', 'format': writer.book.add_format({'left': 2})})
    for wi in range(len(Activities().get_regular())):
        writer.sheets['Roles'].conditional_format(f'{words[wi]}{roles_height+1}', {'type': 'blanks', 'format': writer.book.add_format({'top': 2})})

    for row in range(len(reduced_df) + 100):
        writer.sheets['Calendar'].set_row(row, None, writer.book.add_format({'bg_color': '#FFFFFF'}))
    for row in range(100):
        writer.sheets['Roles'].set_row(row, None, writer.book.add_format({'bg_color': '#FFFFFF'}))
    writer.close()



def initialize(current_date, hist_df, future_weeks=5):
    initial_date = current_date - datetime.timedelta(days=current_date.weekday())
    final_date = initial_date + datetime.timedelta(days=7 * future_weeks)

    wg_members = WgMembers()
    last_hist_week = None
    if hist_df is not None:
        hist_df["Week"] = pandas.to_datetime(hist_df["Week"]).dt.date
        initial_date_ = hist_df.iloc[0]["Week"]
        last_hist_week = hist_df.iloc[-1]["Week"]
        if initial_date_ < initial_date:
            initial_date = initial_date_

    wg_members.initial_date = initial_date
    n_weeks = (final_date - initial_date).days // 7 + 1
    dates_to_compute = []
    date = initial_date
    for i in range(n_weeks):
        date = initial_date + datetime.timedelta(days=7 * i)
        assigned = False
        if hist_df is not None:
            fetched_data = hist_df[hist_df["Week"] == date].to_dict(orient="records")
            if fetched_data:
                del fetched_data[0]["Week"]
                for member_name, member_activity in fetched_data[0].items():
                    m = wg_members.get_member_by_name(member_name)
                    a = activities.get_activity_by_name(member_activity)
                    m.assign(a)
                    assigned = True
        if not assigned and last_hist_week and last_hist_week >= date:
                for m in wg_members.get_members():
                    m.assign(activities.get_anarchy())
                    assigned = True
        if not assigned:
            dates_to_compute.append(date)
    start_end_dates = [initial_date, date]
    return wg_members, dates_to_compute, start_end_dates


def get_avail_members(wg_members: WgMembers, date):
    entries = get_vacations()["entries"]
    available_members = wg_members.get_members()
    for e in entries:
        date_ = datetime.date(year=e['year'], month=e['month'], day=e['day'])
        for i in range(e['n_weeks']):
            if date == date_ + datetime.timedelta(days=7 * i):
                for n in e['names']:
                    for i in range(len(available_members)):
                        if available_members[i].name == n:
                            del available_members[i]
                            break
    return available_members


def assign_tasks(wg_members: WgMembers, avail_members: list[WgMember]):
    if len(avail_members) < len(activities.get_regular()):
        return {m: activities.get_anarchy() for m in wg_members.get_members()}
    
    possible_activities = activities.get_regular() + ([activities.get_vacation()] if len(avail_members) > len(activities.get_regular()) else [])
    all_state_options = []

    for mem_perm in itertools.permutations(avail_members, len(possible_activities)):
        paired = list(zip(possible_activities, mem_perm))
        state_option = {}
        for m in wg_members.get_members():
            for pair in paired:
                if m == pair[1]:
                    state_option[m] = pair[0]
            if m not in state_option:
                state_option[m] = activities.get_vacation()
        all_state_options.append((state_option, wg_members.calculate_fitness(state_option)))

    best = min(all_state_options, key=lambda x: x[1])[0]
    for m, a in best.items():
        m.assign(a)


def swap_members(wg_members: WgMembers, date):
    swaps = get_swaps()['entries']
    for e in swaps:
        date_ = datetime.date(year=e['year'], month=e['month'], day=e['day'])
        if date == date_:
            m1 = wg_members.get_member_by_name(e['name1'])
            m2 = wg_members.get_member_by_name(e['name2'])
            wg_members.swap(m1, m2)


def get_string_by_activities(names_dict, warning=False):
    string = ''
    activities = Activities()
    all_vacation = True
    for name, activity in names_dict.items():
        if activity == activities.get_activity_by_name("Management").name and warning:
            string += f'❗⚠ Manager: {name} ⚠❗\n'
    for name, activity in names_dict.items():
        if activity == activities.get_vacation().name or activity == activities.get_activity_by_name("Management").name:
            continue
        else:
            for a in activities.get_regular():
                if a.name == activity:
                    all_vacation = False
                    string += f'{name}: {activity} {a.emoticons}\n'
    if all_vacation:
        string += f'Total anarchy {activities.get_anarchy().emoticons}'
    else:
        string += f'For the others, {activities.get_vacation().emoticons} !'
    return string


def get_weekly_text(df: DataFrame, date_now, n_weeks=4):
    names = {x: [] for x in df.columns.to_list()[1:]}
    dt = datetime.datetime.now()
    date_now = (dt - datetime.timedelta(days=dt.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    prev_row = None
    for row in df.to_numpy():
        date = datetime.datetime.combine(row[0], datetime.datetime.min.time())
        if date > date_now:
            for name, i in zip(names, range(1, len(names) + 1)):
                names[name].append(prev_row[i])
        prev_row = row
    future_activities_dict = [{k: v[i] for k, v in names.items()} for i in range(min(n_weeks, len(list(names.values())[0])))]
    string = f'This week ({date_now.date().strftime("%d-%m-%y")}):\n'
    string += get_string_by_activities({k: v[0] for k, v in names.items()}, warning=True)
    return string, future_activities_dict


def generate_plan(current_date=None, future_weeks=10):
    if current_date is None:
        current_date = datetime.datetime.now().date()
    current_date = current_date - datetime.timedelta(days=current_date.weekday())

    hist_df = load_history()
    wg_members, dates_to_compute, start_end_dates = initialize(current_date, hist_df, future_weeks)
    for date in dates_to_compute:
        available_members = get_avail_members(wg_members, date)
        assign_tasks(wg_members, available_members)
        swap_members(wg_members, date)
    update_history(hist_df, wg_members, current_date)
    save_plan(wg_members, current_date, start_end_dates)

    text, future_activities = get_weekly_text(wg_members.to_df(), current_date)
    return text, future_activities


if __name__ == "__main__":
    current_date = datetime.datetime.now().date()
    future_weeks = 10  # Unless history contains more recent data, the bac will compute <future_weeks>+1 weeks starting from current_date
    text, future_activities = generate_plan(current_date, future_weeks)
