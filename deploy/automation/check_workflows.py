"""Deterministic guardrails; owner review is still required for policy changes."""

import copy
import json
from pathlib import Path
import re

import yaml


class WorkflowLoader(yaml.SafeLoader):
    # YAML 1.1 treats the GitHub key 'on' as a boolean. Only true/false are bools.
    yaml_implicit_resolvers = copy.deepcopy(yaml.SafeLoader.yaml_implicit_resolvers)


for key, resolvers in WorkflowLoader.yaml_implicit_resolvers.items():
    WorkflowLoader.yaml_implicit_resolvers[key] = [
        (tag, regex) for tag, regex in resolvers if tag != "tag:yaml.org,2002:bool"
    ]
WorkflowLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool", re.compile(r"^(?:true|false)$"), list("tf")
)


def mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ValueError(f"Duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


WorkflowLoader.add_constructor("tag:yaml.org,2002:map", mapping)


def read_workflow(path):
    return yaml.load(path.read_text(), Loader=WorkflowLoader)


def check(root):
    expected = json.loads((root / "deploy/automation/workflow-policy.json").read_text())
    workflow = read_workflow(root / ".github/workflows/tests.yml")
    assert workflow["on"] == {"pull_request": None, "push": {"branches": ["main"]}}, "Test triggers changed"
    assert workflow["permissions"] == {"contents": "read"}, "Workflow permissions changed"
    assert workflow["jobs"]["deploy"] == expected["deploy"], "Deployment job differs from reviewed policy"
    assert workflow["jobs"]["deployment-policy"] == expected["deployment-policy"], "Policy job changed"
    assert set(workflow) == {"name", "on", "permissions", "jobs"}, "Unexpected workflow settings"
    assert set(workflow["jobs"]) == {"tests", "deployment-policy", "deploy"}, "Unexpected job"
    for path in (root / ".github/workflows").glob("*.*"):
        data = read_workflow(path)
        assert not ({"pull_request_target", "workflow_run"} & data["on"].keys()), "Privileged trigger forbidden"
        assert data.get("permissions") == {"contents": "read"}, "Unexpected workflow permissions"
        for name, job in data["jobs"].items():
            if path.name == "tests.yml" and name == "deploy":
                continue  # Entire job is compared above, including inline shell.
            assert job.get("runs-on") == "ubuntu-latest", "Only GitHub-hosted jobs allowed"
            assert "uses" not in job and "environment" not in job, "Unexpected reusable workflow/environment"
            assert job.get("permissions", {"contents": "read"}) == {"contents": "read"}, "Unexpected job permissions"
            raw = json.dumps(job)
            assert not re.search(r"DEPLOY_|TS_DEPLOY|tailscale|id-token|secrets\s*\[", raw, re.I), "Deployment authority outside deploy job"
            # The existing browser demo has separate, unrelated Cloudflare secrets.
            if "secrets." in raw:
                assert path.name == "browser-demo-deploy.yml" and name == "deploy", "Unexpected secrets"
                assert job.get("if") == "github.ref == 'refs/heads/main'", "Demo branch guard changed"
                assert set(re.findall(r"secrets\.([A-Z_]+)", raw)) <= {"CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"}, "Unexpected demo secret"
            for step in job.get("steps", []):
                if "uses" in step:
                    assert step["uses"] in expected["actions"], "Unapproved or mutable action reference"
    assert (root / ".github/CODEOWNERS").read_text().splitlines()[-1] == "* @CarlosBorroto", "Owner gate changed"


if __name__ == "__main__":
    check(Path(__file__).resolve().parents[2])
    print("Deployment workflow policy passed.")
