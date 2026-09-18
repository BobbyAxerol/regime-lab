"""TE-03 lineage: a Selection must be ready after its cutoff and carry params."""
from __future__ import annotations

import pytest

from crypto_regime_lab.experiments.time_edge_contracts import ContractError
from crypto_regime_lab.time_edge.schedule import Selection


def test_selection_requires_ready_after_cutoff_and_parameters():
    with pytest.raises(ContractError):
        Selection("s1", "2021-01-01T00:00:00+00:00", "2020-12-31T00:00:00+00:00", {"a": 1}, "m1").validate()
    with pytest.raises(ContractError):
        Selection("s2", "2021-01-01T00:00:00+00:00", "2021-01-02T00:00:00+00:00", {}, "m1").validate()
    Selection("s3", "2021-01-01T00:00:00+00:00", "2021-01-02T00:00:00+00:00", {"a": 1}, "m1").validate()
