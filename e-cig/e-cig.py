from resources import *


class Aroma:
    aroma1 = Mixture('aroma1', {base_pg: 1.}, d_price=0.3)
    aroma2 = Mixture('aroma2', {base_pg: 1.}, d_price=0)
    cavendish = Mixture('cavendish', {base_pg: 1.}, d_price=0.3)
    virginia = Mixture('virginia', {base_pg: 1.}, d_price=0.3)
    latakia = Mixture('latakia', {base_pg: 1.}, d_price=0.3)
    decomposed = Mixture('decomposed', {base_pg: 1}, d_price=1)


# -------------- NICOTINE blend definition ----------------------------------------------------------------
base_nico = Blend('NICO', fluids={prime_vg: 1.}, nico_concentration=0.1, fluidity=34.2, d_price=0.29)

# -------------- LIQUID creation --------------------------------------------------------------------------

liquid = Liquid(p_pg=0.5, p_vg=0.5, p_w=0, nico=4, base_nico=base_nico,
                mixtures={Aroma.aroma1: 0.10})
new_mixture = liquid.compose(name='liquid0', ref={'tot': 1040})

composition = liquid.get_composition(print_=True)

