# -*- coding: utf-8 -*-
"""Run every platform test script serially with deterministic UTF-8 I/O."""
import argparse
import json
import os
import subprocess
import sys
import time


HERE = os.path.dirname(os.path.abspath(__file__))


def run_all(timeout=600):
    files = sorted(
        os.path.join(HERE, name)
        for name in os.listdir(HERE)
        if name.endswith(".py") and name != os.path.basename(__file__)
    )
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    results = []
    started = time.time()
    for path in files:
        before = time.time()
        try:
            proc = subprocess.run(
                [sys.executable, path],
                cwd=os.path.dirname(HERE),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env=env,
            )
            results.append({
                "test": os.path.basename(path),
                "status": "pass" if proc.returncode == 0 else "fail",
                "returncode": proc.returncode,
                "seconds": round(time.time() - before, 3),
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            })
        except subprocess.TimeoutExpired as exc:
            results.append({
                "test": os.path.basename(path),
                "status": "timeout",
                "returncode": None,
                "seconds": round(time.time() - before, 3),
                "stdout": exc.stdout or "",
                "stderr": exc.stderr or "",
            })
    passed = sum(r["status"] == "pass" for r in results)
    return {
        "summary": {
            "total": len(results),
            "passed": passed,
            "failed": len(results) - passed,
            "seconds": round(time.time() - started, 3),
            "mode": "single_agent_sequential",
        },
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="平台全量串行回归")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = run_all(args.timeout)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for item in report["results"]:
            print("%-7s %6.2fs %s" % (
                item["status"].upper(), item["seconds"], item["test"]))
            if item["status"] != "pass":
                tail = (item["stdout"] + "\n" + item["stderr"]).splitlines()[-30:]
                for line in tail:
                    print("    " + line)
        summary = report["summary"]
        print("SUMMARY total=%d passed=%d failed=%d seconds=%.2f mode=%s" % (
            summary["total"], summary["passed"], summary["failed"],
            summary["seconds"], summary["mode"]))
    sys.exit(1 if report["summary"]["failed"] else 0)


if __name__ == "__main__":
    main()
