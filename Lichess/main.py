import seaborn as sns
from game_retrieval import get_games, get_chess_com_games
from game_util import GameCollection
from matplotlib import pyplot as plt
from rating_conversion import *


update, player = False, 'shapelessguy'
games = get_games(update=update, player=player) + get_chess_com_games(update=update, player=player)
games = GameCollection(player=player, games=games, conversion=Conversion(get_conversion_tables()))
df = games.to_df()

blitz = df[df['Speed'] == 'blitz']
sns.lineplot(data=blitz, x='Date', y='Lichess_rating', hue='Platform')
plt.show()
