import math
import numpy as np
import pandas as pd
pd.set_option("display.colheader_justify", "center")
pd.set_option('display.max_columns', None)
pd.set_option('display.max_rows', None)
pd.set_option('display.width', None)


def digit_round(x, significance=4):
    x = float(x)
    if abs(x) < 10**-32:
        return 0.00
    lev = int(math.floor(math.log10(abs(x))))
    rounded = round(x, significance - lev)
    return rounded


class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


class Fluid:
    def __init__(self, name, density):
        self.name = name
        self.density = density  # g/ml


class Blend:
    def __init__(self, name, fluids, nico_concentration, fluidity=None, d_price=0.):
        """
        Returns a full operative blend used to create Mixtures.

        Parameters:
                name (str): Name of the blend
                fluids (dict[Fluid, float]): Shape -> [fluid, concentration]
                nico_concentration (float): Nicotine in g/ml
                fluidity (float): Fluidity in terms of drops/ml (25°C)
                d_price (float): Price per ml of product
        """
        if sum(fluids.values()) != 1:
            raise Exception("Fluid concentrations don't sum to 1")
        self.name = name
        self.fluids = fluids
        self.nico_concentration = nico_concentration  # g/ml
        self.density = nico_concentration + sum([v * k.density for k, v in fluids.items()])
        self.fluidity = fluidity  # drops/ml (25°C)
        self.d_price = d_price  # €/ml

    def __str__(self):
        string = f"BLEND_{self.name}"
        return string


class Mixture:
    def __init__(self, name='?', elements=None, d_price=None, trace=None, liquid=None):
        """
        Returns a Mixture used to create Liquids.

        Parameters:
                name (str): Name of the mixture
                elements (dict[Blend, float]): Dictionary containing blends and concentrations
                d_price (float): Price per ml of product
        """
        if elements is None:
            raise Exception('Mixtures need to have at least one element!')
        if digit_round(sum(elements.values()), 4) != 1:
            raise Exception("Blend concentrations don't sum to 1")
        if trace is None:
            trace = {}
        self.name = name
        self.elements = elements
        self.density = sum([el.density * c for el, c in elements.items()])
        if d_price is None:
            self.d_price = sum([el.d_price * c for el, c in elements.items()])
        else:
            self.d_price = d_price
        self.fluidity = sum([k.fluidity * v for k, v in self.elements.items()])
        self.trace = trace
        self.liquid = liquid

    @staticmethod
    def get_sub_mixtures(trace=None, root=True, verbose=True):
        sub_mixtures = {}
        for k in trace:
            sub_sub = k.get_sub_mixtures(k.trace, root=False)
            if len(sub_sub) == 0:
                sub_mixtures[k] = sub_mixtures.get(k, 0) + trace[k]
            for k_ in k.get_sub_mixtures(k.trace, root=False):
                if k_ in trace.keys():
                    if root and verbose:
                        print(f'WARNING: sub-mixture {k_.name.upper()} already in {k.name.upper()}')
                sub_mixtures[k_] = sub_mixtures.get(k_, 0) + sub_sub[k_] * trace[k]
        if root:
            mix_to_add = {k: digit_round(2 * trace[k] - sub_mixtures[k], 6) for k in sub_mixtures if k in trace}
            mix_to_add = {**trace, **mix_to_add}
            return sub_mixtures, mix_to_add
        return sub_mixtures

    def get_nicotine(self):
        # Returns the quantity of nicotine in grams
        return sum([k.nico_concentration * v for k, v in self.elements.items()])

    def get_nicotine_liquid(self, base_nico):
        # Returns the quantity of liquid nicotine in ml
        return self.get_nicotine() / base_nico.nico_concentration

    def to_dict(self):
        dict_ = {}
        for k, v in self.elements.items():
            dict_[k.name] = v
        for k, v in self.get_sub_mixtures(self.trace, verbose=False)[0].items():
            dict_[k.name] = digit_round(v, 4)
        return dict_

    def __str__(self):
        string = f"MIXTURE:\n"
        for k, v in self.elements.items():
            string += f" - {k}: {v}\n"
        for k, v in self.get_sub_mixtures(self.trace, verbose=False)[0].items():
            string += f" - sub-mixture: {k.name} | concentration: {v}\n"
        return string


class Liquid:
    def __init__(self, p_pg, p_vg, p_w, nico, base_nico, mixtures={}):
        """
        Returns a new Mixture used to create Liquids.

        Parameters:
                p_pg (float): Percentage of PG
                p_vg (float): Percentage of VG
                p_w (float): Percentage of Water
                nico (float): Nicotine in mg/ml
                base_nico (Blend): Custom Nicotine blend
                mixtures (dict[Mixture, float]): Dictionary containing mixtures and concentrations
        """
        if p_pg + p_vg + p_w != 1:
            raise Exception("Fluid percentages don't sum to 1")
        if sum(mixtures.values()) > 1:
            raise Exception("Mixture percentages sum to a number greater than 1.")
        self.mixtures = mixtures
        self.p_pg = p_pg
        self.p_vg = p_vg
        self.p_w = p_w
        self.nico = nico
        self.base_nico = base_nico
        self.composition = None
        self.name = None

    @staticmethod
    def convert_to_mass(dict_ml):
        out = {}
        for k, v in dict_ml.items():
            out[k] = v * k.density
        return out

    @staticmethod
    def convert_to_drops(dict_ml):
        out = {}
        for k, v in dict_ml.items():
            out[k] = k.fluidity * v
        return out

    @staticmethod
    def convert_to_price(dict_ml):
        out = {}
        for k, v in dict_ml.items():
            out[k] = v * k.d_price
        return out

    @staticmethod
    def to_df(to_add, mult):
        array = []
        index = ['Volume(ml)', 'Mass(g)', '~drops', 'Price(€)']
        columns = [k for k in to_add] + ['Tot']
        rounding = [4, 4, -99, 2]
        for blend in to_add:
            array.append([digit_round(x * mult, i) if i != -99 else int(x * mult) for x, i in zip(to_add[blend], rounding)])
        array.append([digit_round(x, 2) for x in np.array([[x * mult for x in to_add[k]] for k in to_add]).sum(axis=0)])
        array = np.array(array).T
        df = pd.DataFrame(array, index=index, columns=columns)
        return df

    def get_composition(self, tot_ingredients, to_add):
        name = f' -> {self.name}' if self.name is not None else ''
        string = f'\nCOMPOSITION{name}:\n\n'
        comp = self.composition.to_dict()
        tot_quantity = comp["Tot"][list(comp["Tot"])[0]]
        
        tot_ = {k.name: v for k, v in tot_ingredients.items()}
        first_row = []
        for blend in to_add:
            plus = ""
            blend_ = blend.replace(" (to add)", "")
            if tot_.get(blend_, False):
                t = tot_[blend_] * tot_quantity
                incr = to_add[blend].iloc[0] / t * 100
                incr = int(incr * 10) / 10
                plus = f"+{incr}%"
            first_row.append(plus)
        first_row = pd.DataFrame([first_row + [""] * (self.composition.shape[1] - len(first_row))], columns=self.composition.columns, index=["Increase"])

        cmp = self.composition.copy()
        cmp = pd.concat([first_row, cmp])

        lines = cmp.to_string(col_space=15).split('\n')
        for i in range(len(lines)):
            if 'Increase' in lines[i]:
                lines[i] = bcolors.BOLD + lines[i] + bcolors.ENDC
            elif 'Volume(ml)' in lines[i]:
                lines[i] = bcolors.OKCYAN + lines[i] + bcolors.ENDC
            elif 'Mass(g)' in lines[i]:
                lines[i] = bcolors.WARNING + lines[i] + bcolors.ENDC
            elif '~drops' in lines[i]:
                lines[i] = bcolors.OKBLUE + lines[i] + bcolors.ENDC
            elif 'Price(€)' in lines[i]:
                lines[i] = lines[i]
        string += '\t' + '\n\t'.join(lines) + '\n'
        print(string)
        return self.composition

    def is_composable(self):
        mixtures_to_add = Mixture.get_sub_mixtures(trace=self.mixtures, root=True, verbose=False)[1]
        overflow = ''
        for k, v in mixtures_to_add.items():
            if v < 0:
                overflow += f'  Too much {k.name} to handle.\n'
        if overflow != '':
            overflow = 'Mixtures overflow!\n' + overflow + '->  Lower their concentrations in the mixtures.'
            raise Exception(overflow)

        # Blends coming from the pool of mixtures
        ingredients = {}
        for k, v in mixtures_to_add.items():
            for k_n, v_n in k.elements.items():
                ingredients[k_n] = ingredients.get(k_n, 0) + v * v_n

        # Minimum nicotine due to the mixtures (concentration of base nico per ml)
        min_nico_concentration = sum([k.get_nicotine_liquid(self.base_nico) * v for k, v in mixtures_to_add.items()])

        # Minimum desirable nicotine level possible (mg / ml)
        min_possible_concentration = round(min_nico_concentration * (self.base_nico.nico_concentration * 1000), 2)

        # Nicotine (g per ml) to add to reach the desired level
        gap_nico_percentage = self.nico / (self.base_nico.nico_concentration * 1000) - min_nico_concentration

        if gap_nico_percentage < 0:
            raise Exception(f'Nicotine overflow! -> Minimum concentration: {min_possible_concentration}mg/ml')

        # Amount of liquids coming from only mixtures
        primes = {}
        for k, v in ingredients.items():
            for k_n, v_n in k.fluids.items():
                primes[k_n] = primes.get(k_n, 0) + v * v_n
        for k, v in primes.items():
            if primes[k] > 1:
                raise Exception(f'Mixture overflow! - caused by too much {k.name} to utilize.')

        # primes = amount of liquids coming from mixtures AND nicotine
        for k, v in self.base_nico.fluids.items():
            primes[k] = primes.get(k, 0) + v * gap_nico_percentage
            if primes[k] > 1:
                raise Exception(f'Nicotine overflow! - caused by too much {k.name} to utilize.')

        min_p_pg = primes.get(prime_pg, 0)
        min_p_vg = primes.get(prime_vg, 0)
        min_p_water = primes.get(prime_water, 0)
        if min_p_pg + min_p_vg + min_p_water > 1:
            raise Exception(f'Base overflow! - too much nicotine and/or mixture.')
        if self.p_pg < min_p_pg:
            raise Exception(f'Base overflow! - caused by too much {prime_pg.name} '
                            f'to utilize -> Min {prime_pg.name}%: {round(min_p_pg, 2)}.')
        if self.p_vg < min_p_vg:
            raise Exception(f'Base overflow! - caused by too much {prime_vg.name} '
                            f'to utilize -> Min {prime_vg.name}%: {round(min_p_vg, 2)}.')
        if self.p_w < min_p_water:
            raise Exception(f'Base overflow! - caused by too much {prime_water.name} '
                            f'to utilize -> Min {prime_water.name}%: {round(min_p_water, 2)}.')
        return min_p_pg, min_p_vg, min_p_water, gap_nico_percentage, ingredients, mixtures_to_add

    # noinspection PyUnresolvedReferences
    def compose(self, name, ref=None, show=False):
        self.name = name
        min_p_pg, min_p_vg, min_p_water, gap_nico_percentage, ingredients, mixtures_to_add = self.is_composable()

        to_add = {}
        if self.p_pg - min_p_pg != 0:
            to_add[base_pg] = self.p_pg - min_p_pg
        if self.p_vg - min_p_vg != 0:
            to_add[base_vg] = self.p_vg - min_p_vg
        if self.p_w - min_p_water != 0:
            to_add[base_water] = self.p_w - min_p_water
        if gap_nico_percentage != 0:
            to_add[self.base_nico] = gap_nico_percentage

        ml = to_add

        tot_ingredients = ingredients.copy()
        for blend in ml:
            tot_ingredients[blend] = tot_ingredients.get(blend, 0) + ml[blend]

        g = self.convert_to_mass(to_add)
        drops = self.convert_to_drops(to_add)
        price = self.convert_to_price(to_add)
        to_add = {k.name + ' (to add)': [ml[k], g[k], drops[k], price[k]] for k in to_add}

        mult = 0
        if ref is None:
            mult = 1
        elif 'tot' in ref:
            mult = ref['tot']
        else:
            for el in mixtures_to_add:
                if el in ref:
                    mult = ref[el] / mixtures_to_add[el]
        if mult == 0:
            raise Exception("Insert a valid reference")

        mixtures_g = self.convert_to_mass(mixtures_to_add)
        mixtures_d = self.convert_to_drops(mixtures_to_add)
        mixtures_q = {f'MIX{i+1}-' + k.name: [mixtures_to_add[k], mixtures_g[k], mixtures_d[k],
                                              k.d_price * mixtures_to_add[k]] for i, k in
                      zip(range(len(mixtures_to_add)), mixtures_to_add)}
        for k in mixtures_q:
            to_add[k] = mixtures_q[k]

        to_add = self.to_df(to_add, mult)
        self.composition = to_add

        for k, v in mixtures_to_add.items():
            blends = k.elements
            for blend, v_n in blends.items():
                ml[blend] = ml.get(blend, 0) + v * v_n

        d_price = to_add['Tot'].array[-1] / to_add['Tot'].array[0]
        if show:
            self.get_composition(tot_ingredients, to_add)
        return Mixture(name, tot_ingredients, d_price, trace=mixtures_to_add, liquid=self)


# -------------- Definition of raw materials and basic blends ---------------------------------------------
prime_pg = Fluid('PG', 1.06)
prime_vg = Fluid('VG', 1.28)
prime_water = Fluid('WATER', 1)
base_pg = Blend('PG', fluids={prime_pg: 1}, nico_concentration=0, fluidity=46.4, d_price=0.010)
base_vg = Blend('VG', fluids={prime_vg: 1}, nico_concentration=0, fluidity=28.4, d_price=0.010)
base_water = Blend('WATER', fluids={prime_water: 1}, nico_concentration=0, fluidity=50)
default_base_nico = Blend('NICO', fluids={prime_vg: 0.3, prime_pg: 0.7}, nico_concentration=0.1, fluidity=34.2, d_price=0.29)
default_base = Liquid(p_pg=0.444, p_vg=0.556, p_w=0, nico=4, base_nico=default_base_nico).compose(name=f"Std. base")
