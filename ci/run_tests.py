"""Run unchanged synthetic tests and disclose skips, errors and runtime versions."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
import time
import traceback
import unittest

ROOT = Path(__file__).resolve().parents[1]
SUITES = {
    "development": ("test_backup_compare.py", 20),
    "independent": ("review/test_review.py", 7),
}

class RecordedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.passed_ids = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.passed_ids.append(test.id())

def runtime_metadata():
    run_id = os.environ.get("GITHUB_RUN_ID")
    repo = os.environ.get("GITHUB_REPOSITORY")
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    return {
        "os": platform.system(),
        "os_version": platform.platform(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "requested_python": os.environ.get("CI_REQUESTED_PYTHON"),
        "runner_label": os.environ.get("CI_RUNNER_LABEL", "local validation"),
        "runner_image_os": os.environ.get("ImageOS"),
        "runner_image_version": os.environ.get("ImageVersion"),
        "source_sha256": hashlib.sha256((ROOT / "backup_compare.py").read_bytes()).hexdigest(),
        "commit_sha": os.environ.get("GITHUB_SHA"),
        "run_id": run_id,
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "run_url": server + "/" + repo + "/actions/runs/" + run_id if run_id and repo else None,
    }

def verify_sources():
    manifest = json.loads((ROOT / "ci/source_sha256.json").read_text(encoding="utf-8"))
    for name, expected in manifest.items():
        actual = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError("Source manifest mismatch: " + name)

def run_suite(name):
    filename, expected_count = SUITES[name]
    verify_sources()
    physical_parent = Path(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir()).resolve()
    old_tempdir = tempfile.tempdir
    started = time.monotonic()
    sys.path.insert(0, str(ROOT))
    try:
        with tempfile.TemporaryDirectory(prefix="bc-ci-", dir=str(physical_parent)) as fixture:
            # Resolve macOS /var-style aliases before fixtures are created.
            # This selects a physical temporary path; production/test code is unchanged.
            tempfile.tempdir = str(Path(fixture).resolve())
            spec = importlib.util.spec_from_file_location("ci_" + name, ROOT / filename)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            suite = unittest.defaultTestLoader.loadTestsFromModule(module)
            discovered = suite.countTestCases()
            if discovered != expected_count:
                raise RuntimeError("Unexpected test count: %s, expected %s" % (discovered, expected_count))
            result = unittest.TextTestRunner(
                verbosity=2, resultclass=RecordedResult
            ).run(suite)
            skipped = [
                {"test": test.id(), "reason": reason.replace(fixture, "<synthetic-fixture>")}
                for test, reason in result.skipped
            ]
    finally:
        tempfile.tempdir = old_tempdir
        sys.path.pop(0)
    failed = not result.wasSuccessful() or result.testsRun != expected_count
    status = "FAIL" if failed else ("PASS_WITH_SKIPS" if skipped else "PASS")
    return {
        "suite": name,
        "status": status,
        "expected_tests": expected_count,
        "tests_run": result.testsRun,
        "passed": len(result.passed_ids),
        "skipped_count": len(skipped),
        "skipped": skipped,
        "failures": [test.id() for test, detail in result.failures],
        "errors": [test.id() for test, detail in result.errors],
        "unexpected_successes": [test.id() for test in result.unexpectedSuccesses],
        "expected_failures": [test.id() for test, detail in result.expectedFailures],
        "duration_seconds": round(time.monotonic() - started, 3),
        "full_suite_pass": status == "PASS",
    }

def publish(report):
    out = ROOT / ".ci-results"
    out.mkdir(exist_ok=True)
    (out / (report["suite"] + ".json")).write_text(
        json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
    )
    meta = report["runtime"]
    lines = [
        "## Backup Compare / " + report["suite"],
        "",
        "**Result: " + report["status"] + "**",
        "",
        "| Evidence | Value |", "| --- | --- |",
        "| Runner | " + str(meta["runner_label"]) + " |",
        "| OS | " + meta["os_version"] + " |",
        "| Architecture | " + meta["architecture"] + " |",
        "| Python (actual) | " + meta["python"] + " |",
        "| Python requested | " + str(meta["requested_python"]) + " |",
        "| Runner image | " + str(meta["runner_image_os"]) + " / " + str(meta["runner_image_version"]) + " |",
        "| Tests run / expected | %s / %s |" % (report.get("tests_run", 0), report.get("expected_tests", 0)),
        "| Passed | " + str(report.get("passed", 0)) + " |",
        "| Skipped | " + str(report.get("skipped_count", 0)) + " |",
        "| Failures / errors | %s / %s |" % (len(report.get("failures", [])), len(report.get("errors", []))),
        "| Commit | " + str(meta["commit_sha"]) + " |",
        "| Source SHA256 | " + meta["source_sha256"] + " |",
        "",
        "Run: " + str(meta["run_url"]) + "; attempt: " + str(meta["run_attempt"]),
        "",
        "Skips are untested coverage and are not counted as passed tests.",
        "A green job with PASS_WITH_SKIPS does not establish a full-suite platform pass.",
    ]
    for item in report.get("skipped", []):
        lines.append("- SKIP: " + item["test"] + ": " + item["reason"])
    for key in ("failures", "errors"):
        for test_id in report.get(key, []):
            lines.append("- " + key.upper() + ": " + test_id)
    if "harness_error" in report:
        lines.append("- HARNESS ERROR: " + report["harness_error"])
    rendered = "\n".join(lines) + "\n"
    print(rendered, flush=True)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as stream:
            stream.write(rendered)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", required=True, choices=tuple(SUITES))
    args = parser.parse_args()
    runtime = runtime_metadata()
    print("RUNTIME " + json.dumps(runtime, ensure_ascii=True), flush=True)
    try:
        report = run_suite(args.suite)
    except Exception as exc:
        traceback.print_exc()
        report = {
            "suite": args.suite, "status": "HARNESS_ERROR",
            "expected_tests": SUITES[args.suite][1],
            "harness_error": type(exc).__name__ + ": " + str(exc),
            "full_suite_pass": False,
        }
    report["runtime"] = runtime
    publish(report)
    return 1 if report["status"] in ("FAIL", "HARNESS_ERROR") else 0

if __name__ == "__main__":
    sys.exit(main())

