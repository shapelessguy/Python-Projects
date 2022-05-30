from datetime import datetime
import pandas as pd


class Game:
    # noinspection PyDefaultArgument
    def __init__(self, index, player, game_dict={}):
        self.index = index
        self.platform = 'lichess.org'
        self.player = player
        self.color = ''
        self.rating = ''
        self.lichess_rating = 0
        self.opponent_id = ''
        self.opponent_rating = ''

        self.id = None
        self.rated = 'True'
        self.variant = 'standard'
        self.speed = None
        self.perf = None
        self.createdAt = None
        self.lastMoveAt = None
        self.status = None
        self.players = None
        self.winner = None
        self.moves = None
        self.clock = {'initial': 0, 'increment': 0}
        for k, v in game_dict.items():
            self.__setattr__(k, v)
        self.initialize()

    def initialize(self):
        self.get_players_info()
        self.standardize_info()

    def get_players_info(self):
        if self.players is None:
            return
        if 'user' not in self.players['white']:
            side = 'black'
        else:
            side = 'white' if self.players['white']['user'] == self.player else 'black'
        self.color = side
        opp_side = 'white' if side == 'black' else 'black'
        self.opponent_id = self.players[opp_side]['user'] if 'user' in self.players[opp_side] else '_computer_'
        if self.opponent_id != '_computer_':
            self.opponent_rating = int(self.players[opp_side]['rating'])
        self.rating = int(self.players[side]['rating'])

    def standardize_info(self):
        if self.createdAt is None:
            return
        self.createdAt = datetime.strptime(self.createdAt.split('.')[0].split('+')[0], '%Y-%m-%d %H:%M:%S')
        self.lastMoveAt = datetime.strptime(self.lastMoveAt.split('.')[0].split('+')[0], '%Y-%m-%d %H:%M:%S')
        self.clock['initial'], self.clock['increment'] = int(self.clock['initial']), int(self.clock['increment'])

    def standardize_rating(self, conversion):
        if self.platform == 'chess.com':
            self.lichess_rating = conversion.chess_to_lichess(self.speed, self.rating)
        else:
            self.lichess_rating = self.rating

    def to_array(self):
        array = [self.createdAt, self.platform, self.lastMoveAt, self.rated, self.speed, self.status, self.winner,
                 self.clock['initial'], self.clock['increment'], self.color, self.rating, self.lichess_rating,
                 self.opponent_rating, self.opponent_id,
                 ]
        return array

    def __str__(self):
        opp_info = f'({self.opponent_rating})' if self.opponent_id != '_computer_' else ''
        string = f'{self.index} {self.platform} {self.createdAt} '
        string += f"[{self.color.title()}({self.rating}) vs {self.opponent_id}{opp_info}] -> {self.winner}\n"
        return string


class GameCollection(list):
    # noinspection PyDefaultArgument
    def __init__(self, player, games, conversion=None):
        super().__init__()
        self.conversion = conversion
        for g in games:
            if type(g) == dict:
                self.append(Game(-1, player, g))
            else:
                self.append(g)
        self.sort(key=lambda x: x.createdAt)
        for i in range(len(self)):
            self[i].index = i
            self[i].standardize_rating(conversion)

    def add(self, game):
        self.append(game)

    def to_df(self):
        games = []
        columns = ['Date', 'Platform', 'Last_move', 'Rated', 'Speed', 'Status', 'Winner', 'Time', 'Increment',
                   'Color', 'Rating', 'Lichess_rating', 'Opponent_rating', 'Opponent_id']
        for x in self:
            games.append(x.to_array())
        df = pd.DataFrame(games, columns=columns)
        df.set_index('Date')
        return df

    def __str__(self):
        string = 'All games:\n'
        for x in self:
            string += str(x)
        return string
