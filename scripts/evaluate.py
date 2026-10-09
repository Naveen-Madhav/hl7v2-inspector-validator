"""Run the independently specified 24-case synthetic benchmark and save real results."""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from parser import inspect_message  # noqa: E402
from tests.cases import benchmark_cases  # noqa: E402
from validator import validate  # noqa: E402


def main() -> None:
    rows = []
    for case in benchmark_cases():
        start = perf_counter()
        inspection = inspect_message(case.text)
        report = validate(inspection)
        observed = sorted({issue.rule for issue in report.issues})
        location_matches = not case.expected_location or any(
            issue.location == case.expected_location for issue in report.issues
        )
        passed = (
            observed == sorted(case.expected_rules)
            and location_matches
            and (bool(case.expected_rules) or report.complete)
        )
        rows.append(
            {
                "case": case.name,
                "expected_rules": sorted(case.expected_rules),
                "observed_rules": observed,
                "expected_location": case.expected_location,
                "observed_locations": [issue.location for issue in report.issues],
                "passed": passed,
                "parsed": inspection.parsed,
                "scoped_coverage": report.complete,
                "duration_ms": round((perf_counter() - start) * 1000, 3),
            }
        )
    output = {
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset": "Synthetic only",
        "case_count": len(rows),
        "passed": sum(row["passed"] for row in rows),
        "cases": rows,
    }
    path = ROOT / "docs" / "benchmark_results.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(output, indent=2) + "\n")
    print(
        f"{output['passed']}/{output['case_count']} benchmark cases matched expectations. Results: {path}"
    )
    if output["passed"] != output["case_count"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
