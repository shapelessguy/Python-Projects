import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from resources import *

TOTAL_VOLUME_ML = 250
menthol = Mixture('Menthol', {base_pg: 1.}, d_price=0.05)
aroma = Mixture('Berry Bomb', {base_pg: 1.}, d_price=0.69)
aroma_mix = {default_base: 0.88, aroma: 0.1, menthol: 0.012}

liquid: Liquid = Liquid(p_pg=0.51, p_vg=0.49, p_w=0, nico=3.52, base_nico=default_base_nico, mixtures=aroma_mix)
mixture: Mixture = liquid.compose(name=f"Final {aroma.name}", ref={'tot': TOTAL_VOLUME_ML}, show=True)
