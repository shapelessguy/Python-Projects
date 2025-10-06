from resources import *


class Aroma:
    aroma1 = Mixture('aroma1', {base_pg: 1.}, d_price=0.3)
    aroma2 = Mixture('aroma2', {base_pg: 1.}, d_price=0)
    cavendish = Mixture('cavendish', {base_pg: 1.}, d_price=0.3)
    virginia = Mixture('virginia', {base_pg: 1.}, d_price=0.3)
    latakia = Mixture('latakia', {base_pg: 1.}, d_price=0.3)
    decomposed = Mixture('decomposed', {base_pg: 1}, d_price=1)


# -------------- NICOTINE blend definition ----------------------------------------------------------------
base_nico = Blend('NICO', fluids={prime_vg: 0.3, prime_pg: 0.7}, nico_concentration=0.1, fluidity=34.2, d_price=0.29)

# -------------- LIQUID creation --------------------------------------------------------------------------


base_liquid = Liquid(p_pg=0.5, p_vg=0.5, p_w=0, nico=4, base_nico=base_nico, mixtures={})
base_liquid.compose(name='base', ref={'tot': 700})
base_liquid.get_composition(print_=True)


base = Liquid(p_pg=0.5, p_vg=0.5, p_w=0, nico=4, base_nico=base_nico, mixtures={}).compose(name='base', ref={'tot': 40})
# base = Liquid(p_pg=0.5, p_vg=0.5, p_w=0, nico=4, base_nico=base_nico, mixtures={}).compose(name='base', ref={'tot': 40})
# liquid = Liquid(p_pg=0.5, p_vg=0.5, p_w=0, nico=4, base_nico=base_nico, mixtures={base: 1})
# liquid.compose(name='liquid0', ref={'tot': 100})
# liquid.get_composition(print_=True)

scomposto = Liquid(p_pg=0.5, p_vg=0.5, p_w=0, nico=0, base_nico=base_nico, mixtures={}).compose(name='scomposto', ref={'tot': 100})

liquid = Liquid(p_pg=0.5, p_vg=0.5, p_w=0, nico=4, base_nico=base_nico, mixtures={base: 0.65, scomposto: 0.32})
new_mixture = liquid.compose(name='liquid0', ref={'tot': 60})

composition = liquid.get_composition(print_=True)

