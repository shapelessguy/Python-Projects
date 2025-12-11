import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from resources import *

TOTAL_VOLUME_ML = 250

base: Mixture = default_base.liquid.compose(name=f"Base", ref={'tot': TOTAL_VOLUME_ML}, show=True)
