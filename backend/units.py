"""Unit conversion for the tutor and the UI (SI-based tables; temperature handled separately)."""
from __future__ import annotations

# unit -> (dimension, factor to the dimension's base unit)
_U: dict[str, tuple[str, float]] = {}


def _add(dim: str, table: dict[str, float]) -> None:
    for k, f in table.items():
        _U[k.lower()] = (dim, f)


_add("length", {"m": 1, "km": 1000, "cm": 0.01, "mm": 0.001, "um": 1e-6, "nm": 1e-9, "inch": 0.0254, "in": 0.0254, "ft": 0.3048, "yd": 0.9144,
                "mile": 1609.344, "mi": 1609.344, "ly": 9.4607e15, "au": 1.495978707e11, "angstrom": 1e-10})
_add("mass", {"kg": 1, "g": 1e-3, "mg": 1e-6, "tonne": 1000, "quintal": 100, "lb": 0.45359237, "oz": 0.0283495, "amu": 1.66053907e-27, "u": 1.66053907e-27})
_add("time", {"s": 1, "ms": 1e-3, "us": 1e-6, "min": 60, "h": 3600, "hr": 3600, "day": 86400, "year": 3.15576e7})
_add("speed", {"m/s": 1, "km/h": 1 / 3.6, "kmph": 1 / 3.6, "mph": 0.44704, "knot": 0.514444, "cm/s": 0.01, "c": 299792458})
_add("area", {"m2": 1, "cm2": 1e-4, "km2": 1e6, "mm2": 1e-6, "ha": 1e4, "hectare": 1e4, "acre": 4046.8564224, "ft2": 0.09290304, "bigha": 2508.38})
_add("volume", {"m3": 1, "l": 1e-3, "litre": 1e-3, "ml": 1e-6, "cm3": 1e-6, "cc": 1e-6, "dm3": 1e-3, "gallon": 3.785411784e-3})
_add("force", {"n": 1, "kn": 1000, "dyne": 1e-5, "kgf": 9.80665, "lbf": 4.4482216})
_add("energy", {"j": 1, "kj": 1000, "mj": 1e6, "cal": 4.184, "kcal": 4184, "ev": 1.602176634e-19, "kwh": 3.6e6, "erg": 1e-7, "unit": 3.6e6})
_add("power", {"w": 1, "kw": 1000, "mw": 1e6, "hp": 745.699872})
_add("pressure", {"pa": 1, "kpa": 1000, "atm": 101325, "bar": 1e5, "mmhg": 133.322368, "torr": 133.322368, "psi": 6894.757})
_add("frequency", {"hz": 1, "khz": 1e3, "mhz": 1e6, "ghz": 1e9, "rpm": 1 / 60})
_add("angle", {"rad": 1, "deg": 0.017453292519943295, "degree": 0.017453292519943295, "grad": 0.015707963267948967, "rev": 6.283185307179586})
_add("data", {"b": 1, "kb": 1024, "mb": 1024**2, "gb": 1024**3, "tb": 1024**4, "bit": 0.125})
_add("charge", {"c": 1, "mc": 1e-3, "uc": 1e-6, "e": 1.602176634e-19})
_TEMPS = {"c", "k", "f", "celsius", "kelvin", "fahrenheit"}
_ALIAS = {"celsius": "c", "kelvin": "k", "fahrenheit": "f", "°c": "c", "°f": "f", "m^2": "m2", "m²": "m2", "m^3": "m3", "m³": "m3", "cm^3": "cm3",
          "cm³": "cm3", "cm^2": "cm2", "cm²": "cm2", "km^2": "km2", "km²": "km2", "kmh": "km/h", "ohm": "ohm", "metre": "m", "meter": "m",
          "kilometre": "km", "second": "s", "sec": "s", "hour": "h", "minute": "min", "kilogram": "kg", "gram": "g", "joule": "j", "newton": "n",
          "watt": "w", "pascal": "pa", "hertz": "hz", "ms-1": "m/s", "m s-1": "m/s", "litres": "l", "liter": "l"}


def _norm(u: str) -> str:
    u = u.strip().lower().replace(" ", "")
    return _ALIAS.get(u, u)


def convert(value: float, src: str, dst: str) -> float:
    a, b = _norm(src), _norm(dst)
    if a in _TEMPS and b in _TEMPS:
        kelvin = value + 273.15 if a == "c" else value if a == "k" else (value - 32) * 5 / 9 + 273.15
        return kelvin - 273.15 if b == "c" else kelvin if b == "k" else (kelvin - 273.15) * 9 / 5 + 32
    if a not in _U or b not in _U:
        raise ValueError(f"unknown unit '{src if a not in _U else dst}'")
    if _U[a][0] != _U[b][0]:
        raise ValueError(f"cannot convert {_U[a][0]} ({src}) to {_U[b][0]} ({dst})")
    return value * _U[a][1] / _U[b][1]


def known() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {"temperature": ["c", "k", "f"]}
    for u, (dim, _) in _U.items():
        out.setdefault(dim, []).append(u)
    return out
