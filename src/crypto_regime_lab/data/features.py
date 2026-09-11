"""L03.4 — feature blocks G1-G5 and the training-only scaler (guide 6.4).

Every feature here is trailing-only: the value at bar t uses observations up to
and including t and nothing after. The scaler is fitted on a declared TRAINING
slice and applied forward; fitting it on the full history and then "inferring
forward" is the leak the guide names explicitly.

Intermediate raw aggregates are kept alongside the standardized arrays so a
feature can be recomputed and audited, rather than only its z-score surviving.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# Ratio features mask a zero denominator instead of adding an epsilon: a flat
# window has no direction and no path efficiency, and guide 6.4 requires that to
# be MISSING rather than a number.
EPS = 1e-12
DEFAULT_CLIP = 5.0
MAD_TO_SIGMA = 1.4826

GROUPS = ("G1", "G2", "G3", "G4", "G5")
GROUP_TITLES = {
    "G1": "direction and path shape",
    "G2": "activity / active-flow proxies",
    "G3": "leverage and crowding",
    "G4": "liquidity and absorption",
    "G5": "market coordination",
}


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    group: str
    scope: str                     # "local" (this symbol) or "market" (shared context)
    window: int | None
    requires: tuple[str, ...]
    description: str
    caveat: str = ""

    def as_record(self) -> dict:
        return {"name": self.name, "group": self.group, "scope": self.scope,
                "window": self.window, "requires": list(self.requires),
                "description": self.description, "caveat": self.caveat}


# --------------------------------------------------------------------------
# G1 — direction and path shape
# --------------------------------------------------------------------------

def log_returns(close: pd.Series) -> pd.Series:
    return np.log(close / close.shift(1))


def realized_vol(r: pd.Series, w: int) -> pd.Series:
    """RV_{t,w} = sqrt(sum r_i^2) over the trailing window."""
    return np.sqrt(r.pow(2).rolling(w, min_periods=w).sum())


def direction_descriptor(r: pd.Series, w: int) -> pd.Series:
    """T_{t,w} = sum(r) / sqrt(sum r^2), UNDEFINED on a perfectly flat window.

    A DIRECTION DESCRIPTOR. It is not a t-statistic and must never be reported
    as one (guide 6.4 G1).

    The denominator is masked rather than nudged by an epsilon: a window with no
    variation has no direction, and guide 6.4 requires zero dispersion to be
    missing rather than quietly become strong evidence.
    """
    s = r.rolling(w, min_periods=w).sum()
    q = np.sqrt(r.pow(2).rolling(w, min_periods=w).sum())
    return s / q.where(q > 0)


def path_efficiency(r: pd.Series, w: int) -> pd.Series:
    """E_{t,w} = |sum r| / (sum |r| + eps): separates directional from choppy vol."""
    s = r.rolling(w, min_periods=w).sum().abs()
    a = r.abs().rolling(w, min_periods=w).sum()
    return s / a.where(a > 0)


def downside_ratio(r: pd.Series, w: int) -> pd.Series:
    """Share of realized variation contributed by negative returns.

    A variation ratio. It is NOT a crash probability (guide 6.4 G1).
    """
    down = r.where(r < 0, 0.0).pow(2).rolling(w, min_periods=w).sum()
    total = r.pow(2).rolling(w, min_periods=w).sum()
    return down / total.where(total > 0)


def jump_concentration(r: pd.Series, w: int) -> pd.Series:
    """Largest single squared return as a share of the window's realized variance."""
    largest = r.pow(2).rolling(w, min_periods=w).max()
    total = r.pow(2).rolling(w, min_periods=w).sum()
    return largest / total.where(total > 0)


# --------------------------------------------------------------------------
# G2 — activity / active-flow proxies
# --------------------------------------------------------------------------

def taker_imbalance(taker_buy_base: pd.Series, volume: pd.Series) -> pd.Series:
    """I_t = 2 * V_takerbuy / V - 1, with V == 0 left UNDEFINED.

    Not "net capital inflow": every trade has two sides (guide 6.4 G2).
    """
    out = 2.0 * taker_buy_base / volume.replace(0.0, np.nan) - 1.0
    return out


def log_activity_ratio(value: pd.Series, w: int) -> pd.Series:
    """log(current / trailing median), undefined where the reference is zero."""
    reference = value.rolling(w, min_periods=w).median()
    ratio = value / reference.replace(0.0, np.nan)
    return np.log(ratio.where(ratio > 0))


def trade_count_change(trades: pd.Series, w: int) -> pd.Series:
    return log_activity_ratio(trades.astype("float64"), w)


# --------------------------------------------------------------------------
# G3 — leverage and crowding
# --------------------------------------------------------------------------

def delta_log_oi(open_interest: pd.Series) -> pd.Series:
    """Δlog OI. A rise is NOT evidence of "new longs" (guide 6.4 G3)."""
    positive = open_interest.where(open_interest > 0)
    return np.log(positive) - np.log(positive.shift(1))


def basis(perp_close: pd.Series, spot_close: pd.Series) -> pd.Series:
    """B_t = F_t/S_t - 1 on SYNCHRONISED closes; never a future as-of."""
    return perp_close / spot_close.replace(0.0, np.nan) - 1.0


def oi_notional_vs_quantity(oi_quantity: pd.Series, oi_value: pd.Series) -> pd.Series:
    """Implied price behind the notional; separates a price move from a size move."""
    return oi_value / oi_quantity.replace(0.0, np.nan)


def return_oi_interaction(r: pd.Series, d_oi: pd.Series) -> pd.Series:
    """A single preregistered interaction, not a generated polynomial basis."""
    return r * d_oi


# --------------------------------------------------------------------------
# G4 — liquidity and absorption
# --------------------------------------------------------------------------

def relative_spread(spread_bps: pd.Series) -> pd.Series:
    """Spread in basis points. A missing snapshot is NaN, never a zero spread."""
    return spread_bps.astype("float64")


def amihud_impact(r: pd.Series, quote_volume: pd.Series, w: int) -> pd.Series:
    """Rolling mean of |r| / quote volume: an impact PROXY, not a measured impact."""
    ratio = r.abs() / quote_volume.replace(0.0, np.nan)
    return ratio.rolling(w, min_periods=w).mean()


def log_amihud_impact(r: pd.Series, quote_volume: pd.Series, w: int) -> pd.Series:
    """Log of the impact proxy.

    The raw ratio sits around 1e-10 for liquid crypto, which makes its MAD
    degenerate and would see the feature dropped by the scaler for a units
    reason rather than an information reason. The log keeps the same ordering
    with a usable dispersion.
    """
    proxy = amihud_impact(r, quote_volume, w)
    return np.log(proxy.where(proxy > 0))


def range_over_volume(high: pd.Series, low: pd.Series, quote_volume: pd.Series,
                      w: int) -> pd.Series:
    rng = (high - low) / quote_volume.replace(0.0, np.nan)
    return rng.rolling(w, min_periods=w).mean()


# --------------------------------------------------------------------------
# G5 — market coordination
# --------------------------------------------------------------------------

def cross_sectional_dispersion(returns: pd.DataFrame, w: int) -> pd.Series:
    """Cross-sectional standard deviation of contemporaneous returns, smoothed."""
    return returns.std(axis=1, ddof=1).rolling(w, min_periods=w).mean()


def breadth(returns: pd.DataFrame, w: int) -> pd.Series:
    """Share of the eligible universe with a positive trailing return."""
    trailing = returns.rolling(w, min_periods=w).sum()
    return (trailing > 0).sum(axis=1) / trailing.notna().sum(axis=1).replace(0, np.nan)


def rolling_beta_and_residual(local_r: pd.Series, market_r: pd.Series,
                              w: int) -> tuple[pd.Series, pd.Series]:
    """Beta fitted on a PAST window only; the residual is the local component.

    No cross-symbol transform is fitted with any symbol's future observation
    (guide 6.4 G5).
    """
    cov = local_r.rolling(w, min_periods=w).cov(market_r)
    var = market_r.rolling(w, min_periods=w).var()
    beta = cov / var.replace(0.0, np.nan)
    residual = local_r - beta * market_r
    return beta, residual


def common_factor_concentration(returns: pd.DataFrame, w: int) -> pd.Series:
    """Share of variance on the first principal component of a trailing window."""
    out = pd.Series(np.nan, index=returns.index, dtype="float64")
    values = returns.to_numpy()
    for i in range(w - 1, len(returns)):
        block = values[i - w + 1: i + 1]
        if np.isnan(block).any():
            continue
        centred = block - block.mean(axis=0)
        cov = np.cov(centred, rowvar=False)
        eig = np.linalg.eigvalsh(cov)
        total = float(eig.sum())
        if total > 0:
            out.iloc[i] = float(eig[-1] / total)
    return out


# --------------------------------------------------------------------------
# robust scaler
# --------------------------------------------------------------------------

@dataclass
class RobustScaler:
    """z = clip((x - median_train) / (1.4826 * MAD_train + eps), -c, c).

    Fitted on the training slice only. A feature whose training dispersion is
    zero is DROPPED with a reason rather than becoming infinitely strong
    evidence (guide 6.4 scaling).
    """

    clip: float = DEFAULT_CLIP
    median_: dict[str, float] = field(default_factory=dict)
    scale_: dict[str, float] = field(default_factory=dict)
    epsilon_: dict[str, float] = field(default_factory=dict)
    dropped_: dict[str, str] = field(default_factory=dict)
    n_train_: int = 0
    train_range_: tuple[str, str] | None = None

    def fit(self, frame: pd.DataFrame, columns: list[str]) -> "RobustScaler":
        self.n_train_ = int(len(frame))
        if "time" in frame.columns and len(frame):
            self.train_range_ = (str(frame["time"].iloc[0]), str(frame["time"].iloc[-1]))
        for col in columns:
            series = frame[col].astype("float64")
            finite = series[np.isfinite(series)]
            if finite.empty:
                self.dropped_[col] = "no finite observation in the training slice"
                continue
            median = float(finite.median())
            mad = float((finite - median).abs().median())
            scale = MAD_TO_SIGMA * mad
            epsilon = max(1e-9, abs(median) * 1e-9)
            if scale <= epsilon:
                self.dropped_[col] = (f"training dispersion is degenerate "
                                      f"(1.4826*MAD={scale:.3g}); the feature is dropped rather "
                                      "than allowed to dominate")
                continue
            self.median_[col] = median
            self.scale_[col] = scale
            self.epsilon_[col] = epsilon
        return self

    @property
    def active_features(self) -> list[str]:
        return sorted(self.median_)

    def transform(self, frame: pd.DataFrame) -> pd.DataFrame:
        out = pd.DataFrame(index=frame.index)
        for col in self.active_features:
            z = (frame[col].astype("float64") - self.median_[col]) / \
                (self.scale_[col] + self.epsilon_[col])
            out[col] = z.clip(-self.clip, self.clip)
        return out

    def as_record(self) -> dict:
        return {
            "schema": "crypto_regime_lab.robust_scaler.v1",
            "formula": "clip((x - median_train) / (1.4826*MAD_train + eps), -c, c)",
            "clip": self.clip,
            "fitted_on_rows": self.n_train_,
            "training_range": list(self.train_range_) if self.train_range_ else None,
            "median": self.median_,
            "scale": self.scale_,
            "epsilon": self.epsilon_,
            "dropped": self.dropped_,
            "active_features": self.active_features,
            "policy": "fitted on the training slice only; never on the full history",
        }


def group_weights(active: list[str], specs: dict[str, FeatureSpec],
                  weights: dict[str, float] | None = None) -> dict[str, float]:
    """Per-feature weight w_j = omega_g / d_g, so a large block cannot dominate.

    ``d_g`` is the count of ACTIVE features in group g, which is what makes
    adding more features to one block neutral (guide 8.2).
    """
    present = [g for g in GROUPS if any(specs[f].group == g for f in active)]
    if not present:
        return {}
    omega = weights or {g: 1.0 / len(present) for g in present}
    total = sum(omega.get(g, 0.0) for g in present)
    omega = {g: omega.get(g, 0.0) / total for g in present}
    counts = {g: sum(1 for f in active if specs[f].group == g) for g in present}
    return {f: omega[specs[f].group] / counts[specs[f].group] for f in active}
