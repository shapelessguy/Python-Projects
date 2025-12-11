import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from resources import *

TOTAL_VOLUME_ML = 62 # volume of the container

base: Mixture = Liquid(p_pg=0.5, p_vg=0.5, p_w=0, nico=4, base_nico=default_base_nico, mixtures={}).compose(name=f"Base")
longfill: Mixture = Liquid(p_pg=0.5, p_vg=0.5, p_w=0, nico=0, base_nico=default_base_nico, mixtures={}).compose(name='Scomposto')

liquid: Liquid = Liquid(p_pg=0.5, p_vg=0.5, p_w=0, nico=3.5, base_nico=default_base_nico, mixtures={base: 0.647, longfill: 0.323})
new_mixture: Mixture = liquid.compose(name='liquid0', ref={'tot': TOTAL_VOLUME_ML}, show=True)