"""Generic CCR product reference taxonomy (CURATED_REFERENCE_DATA).

Domain metadata about product TYPES (what risk factors/sensitivities a
product family generically carries), never any counterparty's actual
position. Lets the platform explain economic transmission mechanisms
(EVENT -> RISK FACTOR -> PRODUCT -> COUNTERPARTY) without repricing
anything - no custom PFE/NSE engine, no repricer.
"""
import json
from .config import DATA_DIR

_CACHE = None


def load_taxonomy():
    global _CACHE
    if _CACHE is None:
        with open(DATA_DIR / "product_taxonomy.json") as f:
            _CACHE = json.load(f)["products"]
    return _CACHE


def product_info(product_code):
    return load_taxonomy().get(product_code)


def risk_factors_for_product(product_code):
    info = product_info(product_code)
    return info["risk_factors"] if info else []


def sensitivities_for_product(product_code):
    info = product_info(product_code)
    return info["sensitivities"] if info else []
