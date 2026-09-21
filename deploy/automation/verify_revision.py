"""Host-owned authorization gate. Public GitHub reads need no stored API token."""

import json
import re
import sys
import time
from urllib.request import Request, urlopen


REQUIRED_JOBS = {"tests.yml": ("tests", "deployment-policy", "images"), "browser-demo.yml": ("parity",)}


def get_json(path):
    request = Request(
        f"https://api.github.com/repos/{path}",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "frontporch-deploy"},
    )
    with urlopen(request, timeout=20) as response:
        return json.load(response)


def authorized(repository, revision, get=get_json):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Invalid repository")
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Invalid revision")
    if get(f"{repository}/git/ref/heads/main")["object"]["sha"] != revision:
        raise ValueError("Superseded revision")
    for workflow, names in REQUIRED_JOBS.items():
        runs = get(
            f"{repository}/actions/workflows/{workflow}/runs"
            f"?branch=main&event=push&head_sha={revision}&per_page=10"
        )["workflow_runs"]
        runs = [run for run in runs if run["head_sha"] == revision
                and run["event"] == "push" and run["head_branch"] == "main"
                and run["path"] == f".github/workflows/{workflow}"
                and run["repository"]["full_name"] == repository
                and run["head_repository"]["full_name"] == repository]
        if not runs:
            return False
        run = max(runs, key=lambda item: item["id"])
        jobs = get(f"{repository}/actions/runs/{run['id']}/jobs?filter=latest&per_page=100")["jobs"]
        for name in names:
            matches = [job for job in jobs if job["name"] == name]
            if len(matches) != 1 or matches[0]["status"] != "completed":
                return False
            if matches[0]["conclusion"] != "success":
                raise ValueError("Required check failed")
    return True


def main():
    repository, revision = sys.argv[1:]
    # Parity may finish after the Django tests. Bound polling and API requests.
    for attempt in range(16):
        if authorized(repository, revision):
            print("Revision and required jobs verified.")
            return
        if attempt < 15:
            time.sleep(30)
    raise RuntimeError("Required checks did not complete")


if __name__ == "__main__":
    main()
