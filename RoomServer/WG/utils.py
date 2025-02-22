import os
import pandas
import json


wg_folder = os.path.dirname(__file__)


def get_history():
    history_file = f'{wg_folder}/history.csv'
    if os.path.exists(history_file):
        try:
            hist_df = pandas.read_csv(history_file)
            hist_df['Week'] = pandas.to_datetime(hist_df['Week'])
            column_order = ["Week"] + sorted([col for col in hist_df.columns if col != "Week"])
            hist_df = hist_df[column_order]
        except pandas.errors.EmptyDataError:
            return None
    return hist_df


def get_plan():
    plan_file = f'{wg_folder}/cleaning_plan_leo6.xlsx'
    if os.path.exists(plan_file):
        return pandas.read_excel(plan_file)
    return None


def get_vacations():
    vacations_file = f'{wg_folder}/vacations.json'
    vacations = {'entries': []}
    if os.path.exists(vacations_file):
        with open(vacations_file, 'r') as file:
            vacations = json.load(file)
    return vacations


def get_swaps():
    swaps_file = f'{wg_folder}/swaps.json'
    swaps = {'entries': []}
    if os.path.exists(swaps_file):
        with open(swaps_file, 'r') as file:
            swaps = json.load(file)
    return swaps


def get_expenses():
    expenses_file = f'{wg_folder}/expenses.json'
    expenses = {'entries': []}
    if os.path.exists(expenses_file):
        with open(expenses_file, 'r') as file:
            expenses = json.load(file)
    return expenses


def get_blames():
    blames_file = f'{wg_folder}/blames.json'
    blames = {'entries': []}
    if os.path.exists(blames_file):
        with open(blames_file, 'r') as file:
            blames = json.load(file)
    return blames


def save_vacations(vacations):
    vacations_file = f'{wg_folder}/vacations.json'
    if os.path.exists(vacations_file):
        with open(vacations_file, 'w') as file:
            json.dump(vacations, file, indent=4)


def save_swaps(swaps):
    swaps_file = f'{wg_folder}/swaps.json'
    if os.path.exists(swaps_file):
        with open(swaps_file, 'w') as file:
            json.dump(swaps, file, indent=4)


def save_expenses(expenses):
    expenses_file = f'{wg_folder}/expenses.json'
    if os.path.exists(expenses_file):
        with open(expenses_file, 'w') as file:
            json.dump(expenses, file, indent=4)


def save_blames(blames):
    blames_file = f'{wg_folder}/blames.json'
    if os.path.exists(blames_file):
        with open(blames_file, 'w') as file:
            json.dump(blames, file, indent=4)


def expenses_to_xlsx(expenses_df):
    expenses_file = f'{wg_folder}/expenses.xlsx'
    expenses_df.to_excel(expenses_file, index=False)
    return expenses_file
