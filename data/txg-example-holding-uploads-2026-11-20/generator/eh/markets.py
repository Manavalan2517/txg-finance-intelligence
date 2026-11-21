"""Market paths used by the generator: 3-month SAIBOR and exchange rates.

These are rounded, approximate monthly levels chosen to look like the period; they are inputs to a made-up
example, not market data. The Saudi riyal is pegged at 3.75 to the US dollar.
"""
from datetime import date

from .util import rng_for

# 3-month SAIBOR, % a year, monthly average (approximate).
SAIBOR = {
    2020: [2.20, 1.90, 1.40, 1.20, 1.10, 1.00, 0.95, 0.90, 0.88, 0.86, 0.84, 0.83],
    2021: [0.82, 0.81, 0.80, 0.80, 0.79, 0.79, 0.79, 0.80, 0.80, 0.82, 0.85, 0.90],
    2022: [0.95, 1.05, 1.30, 1.80, 2.30, 2.80, 3.10, 3.30, 3.70, 4.30, 5.20, 5.30],
    2023: [5.40, 5.50, 5.60, 5.60, 5.70, 5.90, 6.00, 6.10, 6.20, 6.30, 6.20, 6.20],
    2024: [6.20, 6.20, 6.20, 6.20, 6.20, 6.20, 6.20, 6.10, 5.90, 5.60, 5.50, 5.50],
    2025: [5.50, 5.40, 5.40, 5.40, 5.40, 5.40, 5.40, 5.40, 5.30, 5.10, 5.00, 4.90],
    2026: [4.90, 4.90, 4.80, 4.80, 4.80, 4.70, 4.70, 4.70, 4.60, 4.60, 4.60, 4.60],
}
# EUR in USD, monthly average (approximate).
EURUSD = {
    2020: [1.11, 1.09, 1.11, 1.09, 1.09, 1.13, 1.15, 1.18, 1.18, 1.18, 1.18, 1.22],
    2021: [1.22, 1.21, 1.19, 1.20, 1.21, 1.20, 1.18, 1.18, 1.18, 1.16, 1.14, 1.13],
    2022: [1.13, 1.13, 1.10, 1.08, 1.06, 1.06, 1.02, 1.01, 0.99, 0.98, 1.02, 1.06],
    2023: [1.08, 1.07, 1.07, 1.10, 1.09, 1.08, 1.11, 1.09, 1.07, 1.06, 1.08, 1.09],
    2024: [1.09, 1.08, 1.09, 1.07, 1.08, 1.08, 1.08, 1.10, 1.11, 1.09, 1.06, 1.05],
    2025: [1.04, 1.04, 1.08, 1.12, 1.13, 1.15, 1.17, 1.16, 1.17, 1.16, 1.16, 1.17],
    2026: [1.17, 1.18, 1.16, 1.15, 1.16, 1.17, 1.16, 1.15, 1.16, 1.16, 1.16, 1.16],
}
# CNY per USD, monthly average (approximate).
USDCNY = {
    2020: [6.92, 6.99, 7.01, 7.07, 7.10, 7.08, 7.00, 6.92, 6.81, 6.72, 6.60, 6.54],
    2021: [6.47, 6.46, 6.51, 6.54, 6.43, 6.43, 6.47, 6.48, 6.46, 6.41, 6.39, 6.37],
    2022: [6.36, 6.33, 6.35, 6.43, 6.68, 6.70, 6.74, 6.80, 7.02, 7.20, 7.18, 6.98],
    2023: [6.79, 6.86, 6.90, 6.90, 7.02, 7.17, 7.20, 7.24, 7.30, 7.31, 7.20, 7.12],
    2024: [7.17, 7.19, 7.20, 7.24, 7.23, 7.26, 7.27, 7.15, 7.07, 7.10, 7.21, 7.29],
    2025: [7.30, 7.28, 7.25, 7.29, 7.21, 7.18, 7.17, 7.17, 7.12, 7.12, 7.10, 7.06],
    2026: [7.02, 7.00, 6.98, 6.97, 6.96, 6.95, 6.95, 6.94, 6.93, 6.93, 6.92, 6.92],
}
USD_SAR = 3.75


def saibor(d: date) -> float:
    return SAIBOR[d.year][d.month - 1] / 100.0


def rate_to_sar(currency: str, d: date) -> float:
    """SAR per unit of currency on day d: the monthly level plus a small, reproducible daily wobble."""
    if currency == "SAR":
        return 1.0
    if currency == "USD":
        return USD_SAR
    wob = 1 + (rng_for("fx", currency, d.isoformat()).random() - 0.5) * 0.006
    if currency == "EUR":
        return round(EURUSD[d.year][d.month - 1] * USD_SAR * wob, 6)
    if currency == "CNY":
        return round(USD_SAR / USDCNY[d.year][d.month - 1] * wob, 6)
    raise KeyError(currency)
