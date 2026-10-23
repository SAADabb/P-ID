"""What the workflow can model and draw: every pyDEXPI equipment / piping-component class.

A class is accepted when pyDEXPI has it; its drawing symbol is found through the class hierarchy
(``RadialFan`` -> ``Fan`` -> symbol ``fan``).  An equipment object may name a symbol explicitly
(``symbol: heat_pump``) when the DEXPI class is generic (``CustomEquipment``).
"""

from __future__ import annotations

import inspect
from functools import lru_cache

from pydexpi.dexpi_classes import equipment as _eq
from pydexpi.dexpi_classes import piping as _pp

# symbol family by DEXPI base class, most specific first
_EQUIPMENT_SYMBOLS: list[tuple[str, str]] = [
    ("PlateHeatExchanger", "phx"),
    ("SpiralHeatExchanger", "hx"),
    ("TubularHeatExchanger", "hx"),
    ("AirCoolingSystem", "air_cooler"),
    ("HeatExchanger", "hx"),
    ("CoolingTower", "cooling_tower"),
    ("ProcessColumn", "column"),
    ("Silo", "tank"),
    ("Tank", "tank"),
    ("PressureVessel", "vessel"),
    ("Vessel", "vessel"),
    ("Separator", "vessel"),
    ("Filter", "filter"),
    ("Sieve", "filter"),
    ("Pump", "pump"),
    ("Compressor", "compressor"),
    ("Blower", "fan"),
    ("Fan", "fan"),
    ("Turbine", "turbine"),
    ("Boiler", "boiler"),
    ("SteamGenerator", "boiler"),
    ("Furnace", "heater"),
    ("Heater", "heater"),
    ("Mixer", "mixer"),
    ("Agitator", "mixer"),
    ("Motor", "motor"),
    ("ElectricGenerator", "motor"),
    ("Dryer", "box"),
    ("Centrifuge", "box"),
]

# symbol name -> (width, height) in drawing units
SYMBOL_DIMS: dict[str, tuple[float, float]] = {
    "pump": (38, 38), "compressor": (56, 64), "fan": (44, 44), "turbine": (56, 64), "motor": (36, 36),
    "phx": (50, 78), "hx": (54, 74), "air_cooler": (96, 46), "cooling_tower": (86, 96),
    "tank": (72, 100), "vessel": (58, 104), "column": (52, 150), "filter": (40, 60),
    "boiler": (84, 74), "heater": (76, 86), "mixer": (64, 96), "heat_pump": (148, 92), "box": (112, 56),
}

# symbols an extraction may request explicitly
EXTRA_SYMBOLS = {"heat_pump", "box"}


@lru_cache(maxsize=None)
def equipment_classes() -> frozenset[str]:
    return frozenset(n for n, c in inspect.getmembers(_eq, inspect.isclass) if issubclass(c, _eq.Equipment))


@lru_cache(maxsize=None)
def piping_classes() -> frozenset[str]:
    return frozenset(n for n, c in inspect.getmembers(_pp, inspect.isclass) if issubclass(c, _pp.PipingComponent))


def is_a(cls_name: str, base: str) -> bool:
    """True when the pyDEXPI class ``cls_name`` is ``base`` or derives from it (equipment or piping)."""
    for mod in (_eq, _pp):
        c, b = getattr(mod, cls_name, None), getattr(mod, base, None)
        if inspect.isclass(c) and inspect.isclass(b) and issubclass(c, b):
            return True
    return False


def equipment_symbol(model_class: str, hint: str | None = None) -> str:
    if hint and hint in SYMBOL_DIMS:
        return hint
    for base, sym in _EQUIPMENT_SYMBOLS:
        if is_a(model_class, base):
            return sym
    return "box"


VALVE_KINDS = {
    "valve": "OperatedValve",          # any operated valve class
    "check_valve": "CheckValve",
    "strainer": "Strainer",
    "relief": "SafetyValveOrFitting",
}


def component_class_ok(kind: str, model_class: str) -> bool:
    if kind == "manifold":
        return model_class == "PipeTee"
    if model_class not in piping_classes():
        return False
    if kind == "valve":
        return is_a(model_class, "OperatedValve") or is_a(model_class, "CheckValve") or model_class == "CustomOperatedValve"
    return is_a(model_class, VALVE_KINDS[kind]) or (kind == "relief" and model_class == "CustomSafetyValveOrFitting")


def valve_symbol(model_class: str, function: str | None) -> str:
    if function == "control":
        return "control"
    for base, sym in (("SafetyValveOrFitting", "relief"), ("CustomSafetyValveOrFitting", "relief"), ("CheckValve", "check"),
                      ("BallValve", "ball"), ("AngleBallValve", "ball"), ("ButterflyValve", "butterfly"), ("GlobeValve", "globe"),
                      ("AngleGlobeValve", "globe"), ("PlugValve", "plug"), ("NeedleValve", "globe"), ("Strainer", "strainer")):
        if model_class == base or is_a(model_class, base):
            return sym
    return "gate"  # generic two-way valve (bow-tie)
