import requests
import pandas as pd
import datetime
import pyperclip


emoticons = {
    'Vacation': '⛱️ ⛱️',
    'Kitchen': '🪣🪑',
    'Floor': '🧹🪣🫧',
    'Bathrooms': '🛁🚽',
    'WG management': '💸🧺🍾',
}


def get_df():
    url = 'https://docs.google.com/spreadsheets/d/1-SOeDEYRZosnNmZwkhidMXO5GT9qonZZ/export?format=xlsx'

    # Send a GET request to download the file
    response = requests.get(url)

    if response.status_code == 200:
        # Save the downloaded file
        with open("downloaded_file.xlsx", "wb") as file:
            file.write(response.content)
        
        # Read the Excel file into a DataFrame
        return pd.read_excel("downloaded_file.xlsx", engine='openpyxl')
    else:
        print("Failed to download the file.")
        return None


def get_week_number(date):
    return date.isocalendar()[1], date.year


def get_date_from_week_id(week_id_):
    d = f"{week_id_[1]}-W{week_id_[0]}"
    return datetime.datetime.strptime(d + '-1', "%Y-W%W-%w").date()


def get_string_by_activities(names_dict):
    string = ''
    for name, activity in names_dict.items():
        if activity == 'Vacation':
            continue
        else:
            string += f'{name} -> {activity} {emoticons[activity]}\n'
    string += f'For the others, {emoticons["Vacation"]} !'
    return string


def get_weekly_text():
    df = get_df()
    names = {x: [None, None] for x in df.columns.to_list()[1:]}
    now = datetime.datetime.combine(get_date_from_week_id(get_week_number(datetime.datetime.now().date())), datetime.datetime.min.time())
    prev_row = None
    for row in df.to_numpy():
        date = datetime.datetime.combine(row[0], datetime.datetime.min.time())
        if date >= now:
            for name, i in zip(names, range(1, len(names) + 1)):
                names[name][0] = row[i]
                names[name][1] = prev_row[i]
            break
        prev_row = row

    string = f'This week ({now.date().strftime("%d-%m-%y")}):\n'
    string += get_string_by_activities({k: v[0] for k, v in names.items()})
    string += '\n\n'

    string += f'Next week:\n'
    string += get_string_by_activities({k: v[1] for k, v in names.items()})
    print(string)

pyperclip.copy(get_weekly_text())