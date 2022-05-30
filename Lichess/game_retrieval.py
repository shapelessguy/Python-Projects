import berserk
import json
from datetime import datetime
from dotenv import dotenv_values
import os
from game_util import *
import numpy as np
import requests
import re

session = berserk.TokenSession(dotenv_values('.env')['api_key'])
client = berserk.Client(session=session)


def get_games(update, player):
    gs, new_gs = {}, {}
    start = berserk.utils.to_millis(datetime(2010, 1, 1))
    last_index = -1
    ids = []
    if os.path.exists('games//' + player + '.json'):
        with open('games//' + player + '.json', 'r') as file:
            gs = json.load(file)
            ids = [x['id'] for x in gs.values()]
            last_index = -1 if len(gs) == 0 else max([int(x) for x in gs.keys()])
            if last_index != -1:
                clean_date = gs[str(last_index)]['createdAt'].split('.')[0]
                start = berserk.utils.to_millis(datetime.strptime(clean_date, '%Y-%m-%d %H:%M:%S')) + 60 * 1000
    if update:
        end = berserk.utils.to_millis(datetime.now())
        new_gs = list(client.games.export_by_player(player, since=start, until=end, max=999999))
        new_gs = sorted([g for g in new_gs if g['id'] not in ids], key=lambda x: x['createdAt'])
        for g in new_gs:
            if 'user' in g['players']['white']:
                g['players']['white']['user'] = g['players']['white']['user']['id']
            if 'user' in g['players']['black']:
                g['players']['black']['user'] = g['players']['black']['user']['id']
            if g['status'] == 'outoftime':
                g['status'] = 'timeout'
        new_gs = {i: new_gs[i] for i in range(last_index + 1, len(new_gs))}
        gs = {**gs, **new_gs}
        if len(new_gs) > 0:
            with open('games//' + player + '.json', 'w') as file:
                json.dump(gs, file, indent=4, default=str)
            with open('games//' + player + '.json', 'r') as file:
                gs = json.load(file)
    print(f'User: {player}, #games (Lichess): {len(gs)}, added: {len(new_gs)}')
    return list(gs.values())


def get_chess_com_games(update, player):
    chess_com_games = []
    my_dbs = [db_name for db_name in os.listdir('chess_com_archive')]
    player_db = [db_name for db_name in my_dbs if db_name.split('_')[1] == player]

    new_monthly_dbs = 0
    if update:
        codes_db = [db_name.split('_')[2][:6] for db_name in player_db]
        player_months = [(x[:4], x[4:]) for x in codes_db]
        last_year = max([int(m[0]) for m in player_months]) if len(player_months) > 0 else 2010
        last_month = max([int(m[1]) for m in player_months if m[0] == str(last_year)]) if len(player_months) > 0 else 0
        cur_month, cur_year = datetime.now().month, datetime.now().year
        for y in range(last_year, cur_year + 1):
            for m in range(1, 13):
                if (y == cur_year and m > cur_month) or (y == last_year and m <= last_month):
                    continue
                code = str(y) + ('0' if m < 10 else '') + str(m)
                year, month = str(y), ('0' if m < 10 else '') + str(m)
                url = f'https://api.chess.com/pub/player/{player}/games/{year}/{month}/pgn'
                response = requests.get(url)
                file_name = f"chess_com_archive//ChessCom_{player}_{code}.pgn"
                open(file_name, "wb").write(response.content)
                delete = False
                with open(file_name, 'r') as file:
                    if len(file.readlines()) < 2:
                        delete = True
                if delete:
                    os.remove(file_name)
                new_monthly_dbs += 1

    my_dbs = [db_name for db_name in os.listdir('chess_com_archive')]
    player_db = [db_name for db_name in my_dbs if db_name.split('_')[1] == player]
    for db_name in player_db:
        with open(f'chess_com_archive//{db_name}', 'r') as file:
            gs_lines = []
            lines = file.readlines()
            for line in lines:
                if line == '\n' and gs_lines[-1] == '\n':
                    gs_lines = [lin.replace('\n', '') for lin in gs_lines if lin != '\n']
                    if 'ECO' not in gs_lines[9]:
                        gs_lines = []
                        continue
                    # noinspection PyPep8Naming
                    createdAt = (gs_lines[11][10:-2] + ' ' + gs_lines[17][12:-2]).replace('.', '-') + '.'
                    # noinspection PyPep8Naming
                    lastMoveAt = (gs_lines[18][10:-2] + ' ' + gs_lines[19][10:-2]).replace('.', '-') + '.'
                    players = {'white': {'user': gs_lines[4][8:-2].lower(), 'rating': gs_lines[13][11:-2],
                                         'ratingDiff': 'nan'},
                               'black': {'user': gs_lines[5][8:-2].lower(), 'rating': gs_lines[14][11:-2],
                                         'ratingDiff': 'nan'}}
                    status = gs_lines[16][14:-2].lower()
                    if 'stalemate' in status:
                        status = 'stalemate'
                        winner = 'None'
                    elif 'won' in status:
                        winner, motivation = status.split(' won ')
                        if 'resignation' in motivation:
                            status = 'resign'
                        elif 'checkmate' in motivation:
                            status = 'mate'
                        elif 'time' in motivation:
                            status = 'timeout'
                    else:
                        status = 'draw'
                        winner = 'None'
                    if winner != 'None':
                        winner = 'white' if winner == players['white']['user'] else 'black'
                    time_ctrl = gs_lines[15][14:-2].split('+')
                    clock = {'initial': time_ctrl[0], 'increment': time_ctrl[1] if len(time_ctrl) > 1 else 0}
                    if '/' in clock['initial']:
                        speed = 'correspondence'
                        clock['initial'], clock['increment'] = 0, 0
                    else:
                        in_time = int(clock['initial'])
                        if in_time < 180:
                            speed = 'bullet'
                        elif in_time < 600:
                            speed = 'blitz'
                        elif in_time < 1800:
                            speed = 'rapid'
                        elif in_time < 6000:
                            speed = 'classical'
                        else:
                            speed = 'correspondence'
                    moves = ' '.join(re.sub(r'{.*?}', '', gs_lines[21]).replace('  ', ' ').split(' ')[1::2])

                    game = Game(index=-1, player=player)
                    chess_com_games.append(game)
                    game.createdAt = createdAt
                    game.lastMoveAt = lastMoveAt
                    game.players = players
                    game.status = status
                    game.winner = winner
                    game.moves = moves
                    game.clock = clock
                    game.speed, game.perf = speed, speed
                    game.platform = 'chess.com'
                    game.initialize()
                    gs_lines = []
                else:
                    gs_lines.append(line)
    print(f'User: {player}, #games (Chess.com): {len(chess_com_games)}, monthly dbs added: {new_monthly_dbs}')
    return chess_com_games
