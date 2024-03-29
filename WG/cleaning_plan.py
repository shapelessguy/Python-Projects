import itertools
import os
import random
from collections import Counter

import pandas
import math
import datetime
import pyperclip


in_date_args = (2024, 2, 5)  # Year, month, day
wg_folder = os.path.dirname(__file__)
FUTURE_WEEKS = 10
PAST_WEEKS = 4


class Activities:
    area0 = 'Floor'
    area1 = 'Kitchen'
    area2 = 'Bathrooms'
    area3 = 'Management'
    vacation = 'Vacation'

not_applicable = 'Anarchy'

emoticons = {
    Activities.vacation: '🎊🎉',
    Activities.area0: '🪣🪑',
    Activities.area1: '🧹🪣🫧',
    Activities.area2: '🛁🚽',
    Activities.area3: '💸🧺🍾',
    not_applicable: '😈😈'
}


class WgMembers:
    m1 = 'Claudio'
    m2 = 'Lea'
    m3 = 'Cesare'
    m4 = 'Arman'
    m5 = 'Jaspar'
    m6 = 'Mara'


def get_roles_df():
    len_col = 50
    dict_ = {Activities.area0: [''] * len_col,
             Activities.area1: [''] * len_col,
             Activities.area2: [''] * len_col,
             Activities.area3: [''] * len_col}

    # Floor
    dict_[Activities.area0][0] = "Hallway's floor"
    dict_[Activities.area0][1] = "Kitchen's floor"
    dict_[Activities.area0][2] = "Shoe rack"

    # Kitchen
    dict_[Activities.area1][0] = 'Surfaces + table'
    dict_[Activities.area1][1] = 'Dish space + sink'
    dict_[Activities.area1][2] = 'Oven + Microwave'
    dict_[Activities.area1][3] = 'Stove'

    # Bathrooms
    dict_[Activities.area2][0] = "Big bathroom's floor"
    dict_[Activities.area2][1] = "Big bathroom's steps"
    dict_[Activities.area2][2] = "Small bathroom's floor"
    dict_[Activities.area2][3] = "Shower bathtub + panel"
    dict_[Activities.area2][4] = "Sink"
    dict_[Activities.area2][5] = "Toilets"
    dict_[Activities.area2][6] = "Bath rag"

    # management
    dict_[Activities.area3][0] = 'All trash + bins'
    dict_[Activities.area3][1] = 'TO BUY list'
    dict_[Activities.area3][2] = 'Bottles'
    dict_[Activities.area3][3] = 'Wash laundry'
    dict_[Activities.area3][4] = 'Toilet paper'

    max_len = max([sum([(1 if line != '' else 0) for line in dict_[area]]) for area in dict_])
    dict_ = {a: dict_[a][:max_len] for a in dict_}

    return pandas.DataFrame.from_dict(dict_)


class Vacations:
    def __init__(self, entries=()):
        self.names = []
        for m in wg_members.members:
            self.names.append(m.name)
        self.dates = []
        for entry in entries:
            for date in entry.dates:
                for name in date[0]:
                    self.set(name, date[1])

    def set(self, name, date):
        self.dates.append((name, date))


class Swaps:
    def __init__(self, entries=()):
        self.names = []
        for m in wg_members.members:
            self.names.append(m.name)
        self.dates = []
        for entry in entries:
            for date in entry.dates:
                self.set(date[0][0], date[0][1], date[1])

    def set(self, name1, name2, date):
        self.dates.append((name1, name2, date))


class Entry:
    def __init__(self, names: (tuple or list), in_date: datetime.date, n_weeks: int = 1):
        r_names = [m.name for m in wg_members.members]
        self.names = names
        self.in_date = in_date
        self.n_weeks = n_weeks
        for name in names:
            if name not in r_names:
                raise Exception(f'{str(self)}\n-> Unknown name "{name}"!!')
        if datetime.datetime.combine(get_date_from_week_id(get_week_number(in_date)),
                                     datetime.datetime.min.time()).date() != in_date:
            raise Exception(f'{str(self)}\n-> Initial date is not valid or is not Monday!')
        if n_weeks < 1:
            raise Exception(f'{str(self)}\n-> n_weeks parameter must be greater than 0!')
        datetime_date = datetime.datetime.combine(in_date, datetime.datetime.min.time())
        self.dates = [(names, (datetime_date + datetime.timedelta(days=(i * 7))).date()) for i in range(n_weeks)]

    def __str__(self):
        string = f'Vacation for {", ".join(self.names)} on {self.in_date.strftime("%B %d, %Y")} ' \
                 f'for {self.n_weeks} week(s)'
        return string


class Member:
    def __init__(self, name):
        self.name = name
        self.week = 0
        self.p_activities = {}
        self.log_activities = {}
        self.force_vacation = False
        self.last_real_activity = None
        self.repeat_idx = None
        self.debit = None
        self.spread = None
        self.reset()

    def reset(self):
        self.p_activities = {a: 0 for a in activities}
        self.log_activities = {}
        self.force_vacation = False
        self.last_real_activity = None
        self.repeat_idx = 10000
        self.debit = 0
        self.spread = []

    def get_real_activities(self):
        return {a: self.p_activities[a] for a in activities if a != Activities.vacation}

    def get_n_real_activities(self):
        return sum(self.get_real_activities().values())

    def get_repeat_idx(self, activity):
        repeat_idx = 4
        new_log_activities = self.log_activities.copy()
        new_log_activities[self.week] = activity
        log_without_vacation = {k: v for k, v in new_log_activities.items()}
        for i, v in zip(range(len(log_without_vacation)), log_without_vacation.values().__reversed__()):
            if v == activity:
                repeat_idx = i
                return repeat_idx
        return repeat_idx

    def get_debit(self, activity):
        new_p_activities = self.p_activities.copy()
        new_p_activities[activity] += 1
        working_p_act = {k: v for k, v in new_p_activities.items() if k != Activities.vacation}
        return max(working_p_act.values()) - min(working_p_act.values())

    def get_spread(self, activity):
        new_log_activities = self.log_activities.copy()
        new_log_activities[self.week] = activity
        log_without_vacation = {k: v for k, v in self.log_activities.items() if v != Activities.vacation}
        dist = {}
        spread_dict = {}
        for k, i in zip(log_without_vacation.values(), range(len(log_without_vacation))):
            if k not in spread_dict:
                spread_dict[k] = []
            else:
                spread_dict[k].append(i - dist[k])
            dist[k] = i

        merged_spread = [item for sublist in spread_dict.values() for item in sublist]
        spread = []
        occurrences = Counter(merged_spread)
        for i in range(1, 4):
            spread.append(occurrences.get(i, 0))
        return spread

    def starts_activity(self, activity: str):
        if activity not in activities:
            raise Exception(f"Activity {activity} not in defined activities.")

        self.repeat_idx = self.get_repeat_idx(activity)
        self.debit = self.get_debit(activity)
        self.spread = self.get_spread(activity)

        if activity != Activities.vacation:
            self.last_real_activity = activity
        self.p_activities[activity] += 1
        self.log_activities[self.week] = activity

    def starts_possible_activity(self, taken_activities):
        p_activities = [x for x in self.next_possible_activities() if x not in taken_activities]
        if len(p_activities) == 0:
            p_activities = [x for x in activities if x not in taken_activities]
        activity = p_activities[0]
        taken_activities += [activity]
        self.starts_activity(activity)

    def next_possible_activities(self):
        if self.force_vacation:
            return [Activities.vacation]
        p_activities = {a: self.p_activities[a] for a in activities if a != self.last_real_activity}
        p_activities = [k for k, v in sorted(p_activities.items(), key=lambda x: x[1])]
        return p_activities

    def show_activities(self, summary=False):
        print()
        print(f'Name: {self.name}')
        if summary:
            for k, v in self.p_activities.items():
                print(f'Activity {k}: {v}')
        else:
            for week, a in self.log_activities.items():
                print(f'Week {week}: {a}')
        print()

    def __str__(self):
        return self.name + ': ' + str(self.p_activities)


class WG:
    def __init__(self, *members_name):
        super().__init__()
        self.in_date = None
        self.week = 1
        self.members = []
        for m in members_name:
            self.members.append(Member(m))

    def initialize(self, initial_tasks, in_date: datetime.datetime):
        self.in_date = in_date
        for m in self.members:
            m.week = self.week
        self.week += 1
        for k, v in initial_tasks.items():
            for m in self.members:
                if m.name == k:
                    m.reset()
                    m.starts_activity(v)

    def clear_vacations(self):
        for m in self.members:
            m.force_vacation = False

    def set_vacation(self, name):
        for m in self.members:
            if m.name == name:
                m.force_vacation = True

    def set_swap(self, name1, name2):
        m1, m2 = None, None
        for m in self.members:
            if m.name == name1:
                m1 = m
            elif m.name == name2:
                m2 = m
        if m1 is not None and m2 is not None:
            self.swap(m1, m2)

    @staticmethod
    def brainstorm(members):
        activities_ = members[0].get_real_activities().keys()
        all_permutations = {k: None for k in itertools.permutations(activities_, len(members))}

        # Now, if you want to pair each person with an activity in each permutation:
        for permutation in all_permutations:
            # Zip the current permutation of activities with the people
            # This pairs each person with an activity
            paired = list(zip(members, permutation))
            tot_repeat_idx, tot_deb = 0, 0
            for m, activity in paired:
                tot_repeat_idx += m.get_repeat_idx(activity)
                tot_deb += m.get_debit(activity)
                # m.get_spread(activity)
            t = (tot_repeat_idx, tot_deb)
            fitness = 1000 / (t[0] + 0.1) + t[1]
            all_permutations[permutation] = fitness

        best = min(all_permutations, key=all_permutations.get)
        paired = list(zip(members, best))
        for m, activity in paired:
            m.starts_activity(activity)

    @staticmethod
    def check_swap(m1, m2):
        repeat_idx1 = 10000
        for i, v in zip(range(len(m1.log_activities)), list(m1.log_activities.values().__reversed__())[1:]):
            if v == list(m2.log_activities.values())[-1]:
                repeat_idx1 = i
                break
        repeat_idx2 = 10000
        for i, v in zip(range(len(m2.log_activities)), list(m2.log_activities.values().__reversed__())[1:]):
            if v == list(m1.log_activities.values())[-1]:
                repeat_idx2 = i
                break
        if repeat_idx1 > m1.repeat_idx and (repeat_idx2 > m2.repeat_idx or repeat_idx2 >= 2):
            return repeat_idx1 - m1.repeat_idx, repeat_idx2 - m2.repeat_idx  # gain of the swap
        return -1, -1

    @staticmethod
    def swap(m1, m2):
        activity1, activity2 = m1.log_activities[m1.week], m2.log_activities[m1.week]
        m1.log_activities[m1.week] = activity2
        m2.log_activities[m1.week] = activity1
        m1.p_activities[activity1] -= 1
        m2.p_activities[activity2] -= 1
        m1.p_activities[activity2] += 1
        m2.p_activities[activity1] += 1

    def try_swap_pool(self, members):
        members.sort(key=lambda x: x.repeat_idx, reverse=False)
        m1 = members[0]
        if m1.debit > 2:
            return
        gains = {}
        for i in range(1, len(members)):
            m2 = members[i]
            if m2.debit > 2:
                continue
            gain1, gain2 = self.check_swap(m1, m2)
            if gain1 > 0:
                gains[m2] = (gain1, gain2)
        gains = dict(sorted(gains.items(), key=lambda item: item[1][0], reverse=True))
        if len(gains) > 0:
            best = list(gains.keys())[0]
            candidates = {m: v for m, v in gains.items() if gains[m] == gains[best]}
            candidates = dict(sorted(candidates.items(), key=lambda item: item[1][1], reverse=True))
            best = list(candidates.keys())[0]
            self.swap(m1, best)

    def new_week(self, week_activities=None):
        for m in self.members:
            m.week = self.week
        self.week += 1

        if week_activities is not None:
            for name in week_activities.to_dict():
                for m in self.members:
                    if m.name == name:
                        activity = list(week_activities.to_dict()[name].values())[0].replace(not_applicable, Activities.vacation)
                        m.starts_activity(activity)
        else:
            if sum([(1 if x.force_vacation else 0) for x in self.members]) > 2:
                self.clear_vacations()
                for m in self.members:
                    m.starts_activity(Activities.vacation)
                return
            self.members.sort(key=lambda x: x.get_n_real_activities(), reverse=True)
            self.members.sort(key=lambda x: x.force_vacation, reverse=True)
            for m in self.members[:2]:
                m.starts_activity(Activities.vacation)

            working_members = self.members[2:]
            self.brainstorm(working_members)
            self.clear_vacations()
    
    def save_history(self, df_):
        history_file = f'{wg_folder}/history.csv'
        if os.path.exists(history_file):
            prev_df = pandas.read_csv(history_file)
            prev_df['Week'] = pandas.to_datetime(prev_df['Week'])
            df = df_.copy()
            df['Week'] = pandas.to_datetime(df['Week'])
            df = pandas.concat([prev_df, df])
            df = df.drop_duplicates(subset=['Week'], keep='last')
            df = df.sort_values(by='Week')
        df.iloc[:-FUTURE_WEEKS + 1].to_csv(history_file, index=False)

    def show_calendar(self, save=False):
        def align_center(x):
            return ['text-align: center' for _ in x]

        self.members.sort(key=lambda x: x.name, reverse=False)
        dict_ = {'Week': [(self.in_date + datetime.timedelta(days=(n * 7))).date()
                          for n in range(self.week - 1)][-(FUTURE_WEEKS + 1 + PAST_WEEKS):]}
        
        for week in self.members[0].log_activities:
            n_vac = 0
            for m in self.members:
                if m.log_activities[week] == Activities.vacation:
                    n_vac += 1
            if n_vac == len(self.members):
                for m in self.members:
                    m.log_activities[week] = not_applicable
    
        dict_ = {**dict_, **{m.name: list(m.log_activities.values())[-(FUTURE_WEEKS + 1 + PAST_WEEKS):] for m in self.members}}
        df = pandas.DataFrame.from_dict(dict_)
        df_str = df.to_string(index=False)
        print(df_str)
        if not save:
            return df
        
        self.save_history(df)
        with open(f'{wg_folder}/calendar.txt', 'w') as file:
            file.write(df_str)
        dfs = {'Calendar': df, 'Roles': get_roles_df()}
        print(f'Saving at {wg_folder}/Shared/cleaning_plan.xlsx')
        writer = pandas.ExcelWriter(f'{wg_folder}/Shared/cleaning_plan.xlsx',
                                    engine='xlsxwriter', date_format='dd.mm.yyyy')
        for name, dataframe in dfs.items():
            dataframe.style.apply(align_center, axis=0).to_excel(writer, name, index=False)
        highlight_format = writer.book.add_format({'bg_color': '#FFA500', 'font_color': '#FFFFFF'})
        cell_format = writer.book.add_format({'bg_color': '#FFFFFF'})
        writer.sheets['Calendar'].set_column(0, 6, 20)
        writer.sheets['Roles'].set_column(0, 3, 30)
        writer.sheets['Calendar'].conditional_format('A1:G1000',
                                                     {'type': 'text', 'criteria': 'containing',
                                                      'value': Activities.vacation, 'format': highlight_format})

        for row in range(FUTURE_WEEKS + 1 + PAST_WEEKS + 100):
            writer.sheets['Calendar'].set_row(row, None, cell_format)
        for row in range(100):
            writer.sheets['Roles'].set_row(row, None, cell_format)

        # noinspection PyProtectedMember
        writer._save()
        return df


activities = [Activities.area0, Activities.area1, Activities.area2, Activities.area3, Activities.vacation]
wg_members = WG(WgMembers.m1, WgMembers.m2, WgMembers.m3, WgMembers.m4, WgMembers.m5, WgMembers.m6)


def simulate(n_weeks, initial_date):
    random.seed(0)
    wg_members.initialize({
        WgMembers.m1: Activities.vacation,
        WgMembers.m2: Activities.vacation,
        WgMembers.m3: Activities.area0,
        WgMembers.m4: Activities.area1,
        WgMembers.m5: Activities.area2,
        WgMembers.m6: Activities.area3,
    }, datetime.datetime.strptime(str(initial_date), "%Y-%m-%d"))
    for i in range(n_weeks):
        vacation_idx = []
        m_indexes = list(range(6))
        if random.random() <= 0.3:
            vacation_idx += [random.choice(m_indexes)]
            m_indexes = [x for x in m_indexes if x not in vacation_idx]
            if random.random() <= 0.5:
                vacation_idx += [random.choice(m_indexes)]
                m_indexes = [x for x in m_indexes if x not in vacation_idx]
                if random.random() <= 0.5:
                    vacation_idx += [random.choice(m_indexes)]
        vacation_names = [wg_members.members[v_idx].name for v_idx in vacation_idx]
        for name in vacation_names:
            wg_members.set_vacation(name)
        wg_members.new_week()

    wg_members.show_calendar(save=False)
    for m in wg_members.members:
        print(f'{m.name}: {m.p_activities} debit: {m.debit}  - spread: {m.spread}')


def get_week_number(date):
    return date.isocalendar()[1], date.year


def get_date_from_week_id(week_id_):
    d = f"{week_id_[1]}-W{week_id_[0]}"
    return datetime.datetime.strptime(d + '-1', "%Y-W%W-%w").date()


def get_string_by_activities(names_dict):
    string = ''
    all_vacation = True
    for name, activity in names_dict.items():
        if activity == Activities.vacation:
            continue
        else:
            all_vacation = False
            string += f'{name} -> {activity} {emoticons[activity]}\n'
    if all_vacation:
        string += f'Total anarchy {emoticons[not_applicable]}'
    else:
        string += f'For the others, {emoticons[Activities.vacation]} !'
    return string


def get_weekly_text(df):
    names = {x: [None, None] for x in df.columns.to_list()[1:]}
    now = datetime.datetime.combine(get_date_from_week_id(get_week_number(datetime.datetime.now().date())),
                                    datetime.datetime.min.time())
    prev_row = None
    for row in df.to_numpy():
        date = datetime.datetime.combine(row[0], datetime.datetime.min.time())
        if date > now:
            for name, i in zip(names, range(1, len(names) + 1)):
                names[name][1] = row[i]
                names[name][0] = prev_row[i]
            break
        prev_row = row

    string = f'This week ({now.date().strftime("%d-%m-%y")}):\n'
    string += get_string_by_activities({k: v[0] for k, v in names.items()})
    string += '\n\n'

    string += f'Next week:\n'
    string += get_string_by_activities({k: v[1] for k, v in names.items()})
    return string


def initialize(initial_date):
    # Initialization of WG
    wg_members.initialize({
        WgMembers.m1: Activities.vacation,
        WgMembers.m2: Activities.vacation,
        WgMembers.m3: Activities.area0,
        WgMembers.m4: Activities.area1,
        WgMembers.m5: Activities.area2,
        WgMembers.m6: Activities.area3,
    }, datetime.datetime.strptime(str(initial_date), "%Y-%m-%d"))


def start_bac(vacations, swaps, save: bool):
    date_now = datetime.datetime.combine(get_date_from_week_id(get_week_number(datetime.datetime.now().date())),
                                         datetime.datetime.min.time())
    week_ids = {(date_now + datetime.timedelta(days=(n * 7))).date(): 0 for n in range(-PAST_WEEKS, 1 + FUTURE_WEEKS)}
    print('\nWEEK IDS:')
    for week in week_ids:
        week_ids[week] = get_week_number(week)
        print(f'{week.strftime("%d-%m-%y")} - {week_ids[week]}')
    print()

    datetime_in = datetime.datetime(*in_date_args)
    n_weeks = math.ceil((list(week_ids.keys())[-1] - datetime_in.date()).days / 7)
    initialize(datetime_in.date())

    history_file = f'{wg_folder}/history.csv'
    if os.path.exists(history_file):
        hist_df = pandas.read_csv(history_file)
        hist_df['Week'] = pandas.to_datetime(hist_df['Week'])
    
    for i in range(n_weeks):
        date = (datetime_in + datetime.timedelta(days=((i+1) * 7)))
        pd_date = pandas.to_datetime(date)
        historical = hist_df['Week'].isin([pd_date]).any()
        date = date.date()
        if historical:
            week_activities = hist_df[hist_df['Week'] == pd_date]
            wg_members.new_week(week_activities=week_activities)
        else:
            for name, date_ in vacations.dates:
                if date == date_:
                    wg_members.set_vacation(name)
            wg_members.new_week()
            for name1, name2, date_ in swaps.dates:
                if date == date_:
                    wg_members.set_swap(name1, name2)

    df = wg_members.show_calendar(save=save)
    if df is None:
        return
    pyperclip.copy(get_weekly_text(df))
    return wg_members


if __name__ == '__main__':
    date_in = datetime.datetime(*in_date_args).date()
    simulate(n_weeks=100, initial_date=date_in)
