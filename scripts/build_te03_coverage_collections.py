#!/usr/bin/env python3
"""Bridge prior committed TE-03 target collections with the coverage extension.

The merged artifacts record both source identities and the coverage revision
hash; origins stay strictly appended and no prior target is rewritten.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crypto_regime_lab.time_edge.coverage import merge_coverage_collections  # noqa: E402
from crypto_regime_lab.time_edge.storage import digest, file_digest  # noqa: E402


def reference(relative):
    path = ROOT / relative
    if not path.is_file():
        raise SystemExit("missing bridge input: " + relative)
    return {"path": relative, "sha256": file_digest(path)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage", default="evidence/time_edge_validation_v4/coverage-revisions/TE03-COVERAGE-R01.json")
    parser.add_argument("--prior-targets", default="evidence/time_edge_validation_v4/host-targets-01.json")
    parser.add_argument("--extension-targets", required=True)
    parser.add_argument("--prior-results", default="evidence/time_edge_validation_v4/host-targets-results-01.json")
    parser.add_argument("--extension-results", required=True)
    parser.add_argument("--targets-output", default="evidence/time_edge_validation_v4/host-targets-coverage-01.json")
    parser.add_argument("--results-output", default="evidence/time_edge_validation_v4/host-targets-results-coverage-01.json")
    args = parser.parse_args()
    coverage_ref = reference(args.coverage)
    run_id = "TE-COVERAGE-BRIDGE-" + digest([args.prior_targets, args.extension_targets])[:12]
    targets = merge_coverage_collections(ROOT, prior_refs=[reference(args.prior_targets)],
                                         extension_ref=reference(args.extension_targets),
                                         coverage_ref=coverage_ref, kind="targets",
                                         output=args.targets_output, lab_run_id=run_id)
    results = merge_coverage_collections(ROOT, prior_refs=[reference(args.prior_results)],
                                         extension_ref=reference(args.extension_results),
                                         coverage_ref=coverage_ref, kind="results",
                                         output=args.results_output, lab_run_id=run_id)
    print(json.dumps({"targets": targets, "results": results}, indent=1))


if __name__ == "__main__":
    main()
