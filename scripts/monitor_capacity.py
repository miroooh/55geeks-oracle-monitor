#!/usr/bin/env python3
"""Check OCI Always Free capacity and open one GitHub issue when available.

This script never launches or modifies an instance. Uses an Oracle monitor-only
API key authorized only to manage compute-capacity-reports.
"""
import datetime as dt
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

REGION = "us-sanjose-1"
AD = "wQIc:US-SANJOSE-1-AD-1"
SHAPES = (
    ("Ampere A1 6 GB", {"instanceShape": "VM.Standard.A1.Flex",
                         "instanceShapeConfig": {"ocpus": 1, "memoryInGBs": 6}}),
    ("Ampere A1 4 GB", {"instanceShape": "VM.Standard.A1.Flex",
                         "instanceShapeConfig": {"ocpus": 1, "memoryInGBs": 4}}),
    ("Ampere A1 2 GB", {"instanceShape": "VM.Standard.A1.Flex",
                         "instanceShapeConfig": {"ocpus": 1, "memoryInGBs": 2}}),
    ("Ampere A1 1 GB", {"instanceShape": "VM.Standard.A1.Flex",
                         "instanceShapeConfig": {"ocpus": 1, "memoryInGBs": 1}}),
    ("AMD Micro 1 GB", {"instanceShape": "VM.Standard.E2.1.Micro"}),
)
ALLOWED = {"AVAILABLE", "OUT_OF_HOST_CAPACITY", "HARDWARE_NOT_SUPPORTED", "UNKNOWN_ENUM_VALUE"}
ISSUE_TITLE = "Oracle Always Free capacity AVAILABLE - 55GEEKS San Jose"


class MonitorError(Exception):
    pass


def required_environment():
    required = ("OCI_CLI_TENANCY", "OCI_CLI_CONFIG_FILE")
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise MonitorError("Missing required monitoring secrets: " + ", ".join(missing))
    return os.environ["OCI_CLI_TENANCY"]


def query_capacity(tenancy, shape, request):
    cmd = [
        "oci", "--config-file", os.environ["OCI_CLI_CONFIG_FILE"], "--profile", "DEFAULT", "--auth", "api_key", "compute", "compute-capacity-report", "create",
        "--availability-domain", AD,
        "--compartment-id", tenancy,
        "--shape-availabilities", json.dumps([request], separators=(",", ":")),
        "--region", REGION, "--output", "json",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=70, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MonitorError(f"OCI CLI execution failed for {shape}: {type(exc).__name__}") from exc
    if result.returncode != 0:
        raise MonitorError(f"OCI CLI exited {result.returncode} while checking {shape}; verify key and permissions")
    try:
        entries = json.loads(result.stdout)["data"]["shape-availabilities"]
        matches = [entry for entry in entries if entry.get("instance-shape") == request["instanceShape"]
                   and ("instanceShapeConfig" not in request or
                        (entry.get("instance-shape-config") or {}).get("ocpus") == request["instanceShapeConfig"]["ocpus"]
                        and (entry.get("instance-shape-config") or {}).get("memory-in-gbs") == request["instanceShapeConfig"]["memoryInGBs"])]
        if len(matches) != 1:
            raise ValueError("wrong number of shape results")
        entry = matches[0]
        status = entry["availability-status"]
        if status not in ALLOWED:
            raise ValueError("unknown capacity status")
        count = entry.get("available-count")
        if count is not None and (not isinstance(count, int) or count < 0):
            raise ValueError("invalid available-count")
        return {"shape": shape, "status": status, "count": count}
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        raise MonitorError(f"Unexpected OCI capacity response for {shape}") from exc


def github_api(method, url, token, payload=None):
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + token,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "55geeks-capacity-monitor",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise MonitorError(f"GitHub API returned HTTP {exc.code} during issue notification") from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise MonitorError(f"GitHub issue notification failed: {type(exc).__name__}") from exc


def notify_when_available(results, timestamp):
    if not any(row["status"] == "AVAILABLE" and row["count"] != 0 for row in results):
        return "No shape available; no alert created."
    repo, token = os.getenv("GITHUB_REPOSITORY", ""), os.getenv("GH_TOKEN", "")
    if not re.fullmatch(r"[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+", repo) or not token:
        raise MonitorError("GITHUB_REPOSITORY and GH_TOKEN required for alert")
    endpoint = "https://api.github.com/repos/" + repo + "/issues"
    issues = github_api("GET", endpoint + "?state=open&per_page=100", token)
    if any(item.get("title") == ISSUE_TITLE and "pull_request" not in item for item in issues):
        return "Availability detected; existing open alert issue retained."
    message = [
        "**Oracle capacity is reported AVAILABLE; this is not a reservation.**",
        "",
        f"Checked at (UTC): {timestamp}",
        f"Region: {REGION}; AD: {AD}",
        "",
        "| Shape | Status | Reported available count |",
        "|---|---|---|",
    ]
    message.extend(
        f"| {row['shape']} | {row['status']} | {row['count'] if row['count'] is not None else 'Not provided'} |"
        for row in results
    )
    message.extend([
        "", "Action: verify live capacity and Always Free limits; launch using approved network/SSH configuration.",
        "No VM was launched by the monitor. Do not select a paid alternative.",
    ])
    created = github_api("POST", endpoint, token, {
        "title": ISSUE_TITLE,
        "body": "\n".join(message),
        "assignees": [repo.split("/")[0]],
    })
    return f"Capacity available; opened issue #{created['number']}."


def summarize(results, message, timestamp):
    rows = [
        "## Oracle Always Free capacity", "",
        "Checked (UTC): " + timestamp, "",
        "| Shape | Status | Count |", "|---|---|---|",
    ]
    rows.extend(
        f"| {row['shape']} | {row['status']} | {row['count'] if row['count'] is not None else 'N/A'} |"
        for row in results
    )
    rows.extend(["", message, "", "No server was created by this workflow.", ""])
    report = "\n".join(rows)
    print(report)
    path = os.getenv("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as output:
            output.write(report + "\n")


def main():
    tenancy = required_environment()
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    results = [query_capacity(tenancy, shape, payload) for shape, payload in SHAPES]
    message = notify_when_available(results, timestamp)
    summarize(results, message, timestamp)


if __name__ == "__main__":
    try:
        main()
    except MonitorError as exc:
        print("CAPACITY_MONITOR_FAILED: " + str(exc), file=sys.stderr)
        sys.exit(1)
