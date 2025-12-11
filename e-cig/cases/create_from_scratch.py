import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from resources import *

TOTAL_VOLUME_ML = 100
aroma = Mixture('generic_aroma', {base_pg: 1.}, d_price=0.53)

aroma_mix = {default_base: 0.88, aroma: 0.1}
liquid: Liquid = Liquid(p_pg=0.5, p_vg=0.5, p_w=0, nico=3.52, base_nico=default_base_nico, mixtures=aroma_mix)
mixture: Mixture = liquid.compose(name=f"Final {aroma.name}", ref={'tot': TOTAL_VOLUME_ML}, show=True)