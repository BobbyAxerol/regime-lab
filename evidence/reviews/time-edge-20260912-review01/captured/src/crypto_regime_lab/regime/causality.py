"""T39 — prove the fit and the scaler cannot see past their declared cutoff.

The check is a mutation test: replace everything AFTER the training cutoff with
different numbers, refit, and require the model to come out bit-identical. If it
moves, something upstream of the cutoff read downstream data.

A mutation test that cannot fail proves nothing, which is the trap this module is
built to avoid. ``leaky_fit_for_control`` deliberately fits on the whole array,
and the suite asserts the detector CATCHES it. Without that control, a detector
that always returns "clean" would look like a pass.
"""

from __future__ import annotations

import numpy as np

from .jump_model import centroid_digest, multi_start_fit

MAD_TO_SIGMA = 1.4826


def fit_scaler(train: np.ndarray, *, clip: float = 5.0, eps: float = 1e-12) -> dict:
    """Median/MAD on the TRAINING rows only, matching the LAB-03 convention."""
    train = np.asarray(train, dtype=np.float64)
    median = np.median(train, axis=0)
    mad = np.median(np.abs(train - median), axis=0)
    return {"median": median, "scale": MAD_TO_SIGMA * mad + eps, "clip": float(clip),
            "fitted_rows": int(train.shape[0])}


def apply_scaler(values: np.ndarray, scaler: dict) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    z = (values - scaler["median"]) / scaler["scale"]
    return np.clip(z, -scaler["clip"], scaler["clip"])


def causal_fit(raw: np.ndarray, cutoff: int, *, n_states: int, lambda_jump: float,
               seeds: tuple[int, ...] = (1, 2, 3)) -> dict:
    """The correct thing: scaler AND model see rows [0, cutoff) and nothing else."""
    raw = np.asarray(raw, dtype=np.float64)
    if not 2 <= cutoff <= raw.shape[0]:
        raise ValueError(f"cutoff {cutoff} outside 2..{raw.shape[0]}")
    train_raw = raw[:cutoff]
    scaler = fit_scaler(train_raw)
    z_train = apply_scaler(train_raw, scaler)
    weights = np.full(raw.shape[1], 1.0 / raw.shape[1])
    fit = multi_start_fit(z_train, weights, n_states=n_states, lambda_jump=lambda_jump,
                          seeds=seeds)
    return {"scaler": scaler, "centroids": fit["centroids"], "weights": weights,
            "selected_seed": fit["selected_seed"], "cutoff": cutoff,
            "digest": centroid_digest(fit["centroids"]),
            "scaler_digest": centroid_digest(np.vstack([scaler["median"], scaler["scale"]]))}


def leaky_fit_for_control(raw: np.ndarray, cutoff: int, *, n_states: int, lambda_jump: float,
                          seeds: tuple[int, ...] = (1, 2, 3)) -> dict:
    """DELIBERATELY WRONG: fits the scaler on the whole array, future included.

    Exists only so the mutation detector can be shown to catch a real leak. It is
    never used to produce a model artifact, and a test asserts it is flagged.
    """
    raw = np.asarray(raw, dtype=np.float64)
    scaler = fit_scaler(raw)                       # <-- the leak: whole array
    z_train = apply_scaler(raw[:cutoff], scaler)
    weights = np.full(raw.shape[1], 1.0 / raw.shape[1])
    fit = multi_start_fit(z_train, weights, n_states=n_states, lambda_jump=lambda_jump,
                          seeds=seeds)
    return {"scaler": scaler, "centroids": fit["centroids"], "weights": weights,
            "selected_seed": fit["selected_seed"], "cutoff": cutoff,
            "digest": centroid_digest(fit["centroids"]),
            "scaler_digest": centroid_digest(np.vstack([scaler["median"], scaler["scale"]])),
            "deliberately_leaky": True}


def mutate_future(raw: np.ndarray, cutoff: int, *, seed: int = 99, scale: float = 7.0,
                  shift: float = 11.0) -> np.ndarray:
    """Replace the post-cutoff suffix with something unmistakably different."""
    raw = np.asarray(raw, dtype=np.float64)
    rng = np.random.default_rng(seed)
    out = raw.copy()
    tail = raw.shape[0] - cutoff
    if tail <= 0:
        raise ValueError("nothing after the cutoff to mutate")
    out[cutoff:] = rng.normal(shift, scale, size=(tail, raw.shape[1]))
    return out


def future_suffix_mutation_test(raw: np.ndarray, cutoff: int, *, n_states: int = 3,
                                lambda_jump: float = 1.0,
                                fit_fn=causal_fit, seed: int = 99) -> dict:
    """T39 — refit on a mutated future and require an identical model.

    The precondition matters as much as the result: the mutation must actually
    change the suffix, or "the model did not move" is trivially true.
    """
    raw = np.asarray(raw, dtype=np.float64)
    mutated = mutate_future(raw, cutoff, seed=seed)

    prefix_untouched = bool(np.array_equal(raw[:cutoff], mutated[:cutoff]))
    suffix_changed = not bool(np.array_equal(raw[cutoff:], mutated[cutoff:]))

    before = fit_fn(raw, cutoff, n_states=n_states, lambda_jump=lambda_jump)
    after = fit_fn(mutated, cutoff, n_states=n_states, lambda_jump=lambda_jump)

    centroids_identical = bool(np.array_equal(np.asarray(before["centroids"]),
                                              np.asarray(after["centroids"])))
    scaler_identical = (bool(np.array_equal(before["scaler"]["median"],
                                            after["scaler"]["median"]))
                        and bool(np.array_equal(before["scaler"]["scale"],
                                                after["scaler"]["scale"])))
    leaked = not (centroids_identical and scaler_identical)
    return {
        "schema": "crypto_regime_lab.future_suffix_mutation.v1",
        "cutoff": int(cutoff), "observations": int(raw.shape[0]),
        "mutation_effective": suffix_changed,
        "training_prefix_untouched": prefix_untouched,
        "probe_valid": bool(suffix_changed and prefix_untouched),
        "centroids_identical": centroids_identical,
        "scaler_identical": scaler_identical,
        "leak_detected": leaked,
        "verdict": "LEAK_DETECTED" if leaked else "CAUSAL",
        "digest_before": before["digest"], "digest_after": after["digest"],
        "scaler_digest_before": before["scaler_digest"],
        "scaler_digest_after": after["scaler_digest"],
        "rule": ("a fit that declares a cutoff must be bit-identical when everything after that "
                 "cutoff is replaced. Anything else means the scaler or the model read data it "
                 "declared it could not see (T39)"),
    }


def run_control_pair(raw: np.ndarray, cutoff: int, *, n_states: int = 3,
                     lambda_jump: float = 1.0) -> dict:
    """Run the detector on a causal fit AND on a knowingly leaky one."""
    causal = future_suffix_mutation_test(raw, cutoff, n_states=n_states,
                                         lambda_jump=lambda_jump, fit_fn=causal_fit)
    leaky = future_suffix_mutation_test(raw, cutoff, n_states=n_states,
                                        lambda_jump=lambda_jump, fit_fn=leaky_fit_for_control)
    return {
        "schema": "crypto_regime_lab.mutation_detector_control.v1",
        "causal_fit": causal,
        "deliberately_leaky_fit": leaky,
        "detector_passes_clean_fit": causal["verdict"] == "CAUSAL",
        "detector_catches_known_leak": leaky["verdict"] == "LEAK_DETECTED",
        "detector_is_meaningful": (causal["verdict"] == "CAUSAL"
                                   and leaky["verdict"] == "LEAK_DETECTED"),
        "why_the_control_exists": (
            "a detector that always returns CAUSAL would pass the clean fit too. The known-leaky "
            "fit is the only thing that shows the check can fail"),
    }
