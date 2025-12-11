import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from resources import *

aroma = Mixture('generic_aroma', {base_pg: 1.}, d_price=0.3)

liquid: Liquid = Liquid(p_pg=0.5, p_vg=0.5, p_w=0, nico=3.44, base_nico=default_base_nico, mixtures={aroma: 0.1}).compose(name=f"Final {aroma.name}", ref={aroma: 23}, show=True)
