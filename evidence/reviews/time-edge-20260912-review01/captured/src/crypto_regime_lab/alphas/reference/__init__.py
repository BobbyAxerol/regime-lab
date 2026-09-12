"""Reference (oracle) implementations for the four alphas' indicators.

Plain Python/NumPy, no Numba, no fastmath. These define what a decision *is*;
any accelerated kernel must reproduce them inside the declared tolerance or it
does not ship (guide L02.2).
"""
