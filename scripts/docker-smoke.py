"""Validate a disposable local Compose stack, including restart and backup restore.

This creates fictitious accounts and data. It refuses non-loopback URLs and
Compose projects outside circular-validation*, and never targets user SQLite.
"""
import argparse
import http.cookiejar
import json
from pathlib import Path
import secrets
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


class Client:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))
        self.csrf = ""

    def call(self, method: str, path: str, payload=None, expected: int = 200):
        headers = {"Content-Type": "application/json"}
        if self.csrf:
            headers["X-CSRF-Token"] = self.csrf
        body = json.dumps(payload if payload is not None else {}).encode() if method in {"POST", "PATCH"} else None
        request = urllib.request.Request(self.base + path, data=body, headers=headers, method=method)
        try:
            response = self.opener.open(request, timeout=15)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            assert response.status == expected, f"{method} {path}: HTTP {response.status}, expected {expected}"
            data = response.read()
            return json.loads(data) if data else None


def command(*args: str) -> str:
    result = subprocess.run(args, cwd=ROOT, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def ready(base: str) -> None:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            if Client(base).call("GET", "/api/ready")["ok"]:
                return
        except (OSError, AssertionError):
            time.sleep(0.5)
    raise RuntimeError("Docker application did not become ready within 90 seconds.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--project", default="circular-validation")
    args = parser.parse_args()
    parsed = urllib.parse.urlsplit(args.url)
    if parsed.hostname not in {"127.0.0.1", "localhost"} or parsed.scheme != "http" or parsed.path not in {"", "/"}:
        raise SystemExit("Only a disposable loopback HTTP stack is accepted.")
    if not args.project.startswith("circular-validation"):
        raise SystemExit("The Compose project must start with circular-validation.")
    compose = ["docker", "compose", "--env-file", args.env_file, "-p", args.project, "-f", "compose.yaml", "-f", "compose.postgres.yaml", "-f", "compose.local.yaml"]
    containers = {service: command(*compose, "ps", "-q", service) for service in ("app", "postgres")}
    for container in containers.values():
        if not container:
            raise SystemExit("Start the disposable Compose stack first.")
        metadata = json.loads(command("docker", "inspect", container))[0]
        if metadata["Config"]["Labels"].get("com.docker.compose.project") != args.project:
            raise SystemExit("Container ownership does not match the requested disposable project.")
    suffix = uuid4().hex[:10]
    alice, bob = Client(args.url), Client(args.url)
    ready(args.url)
    users = []
    for client, name in ((alice, "owner"), (bob, "member")):
        result = client.call("POST", "/api/auth/register", {"username": name + suffix, "email": name + suffix + "@epita.fr", "password": secrets.token_urlsafe(32)}, 201)
        client.csrf = result["csrfToken"]
        users.append(result["user"])
    project = alice.call("POST", "/api/projects", {"name": "Validation Docker " + suffix, "key": "D" + suffix[:8].upper()}, 201)
    ticket = alice.call("POST", "/api/issues", {"title": "Ticket Docker persistant", "projectId": project["id"], "isFavorite": True}, 201)
    assert bob.call("GET", "/api/projects") == []
    bob.call("GET", f'/api/issues/{ticket["id"]}', expected=404)
    invitation = alice.call("POST", f'/api/projects/{project["id"]}/invitations', {"email": users[1]["email"]}, 201)
    bob.call("POST", f'/api/invitations/{invitation["id"]}/accept', {}, 204)
    assert bob.call("GET", f'/api/issues/{ticket["id"]}')["isFavorite"] is False
    bob.call("PATCH", f'/api/issues/{ticket["id"]}', {"status": "in_progress"})
    comment = bob.call("POST", f'/api/issues/{ticket["id"]}/comments', {"body": "Commentaire Docker persistant"}, 201)
    alice.call("PATCH", "/api/settings", {"fontSize": "large"})
    assert bob.call("GET", "/api/settings")["fontSize"] == "default"
    command(*compose, "restart", "postgres", "app")
    ready(args.url)
    assert alice.call("GET", f'/api/issues/{ticket["id"]}')["status"] == "in_progress"
    assert bob.call("GET", f'/api/issues/{ticket["id"]}/comments')[0]["body"] == "Commentaire Docker persistant"
    assert alice.call("GET", "/api/settings")["fontSize"] == "large"
    dump_directory = ROOT / ".test-data" / "docker-validation"
    dump_directory.mkdir(parents=True, exist_ok=True)
    backup = dump_directory / (suffix + ".dump")
    database = "circular_restore_" + suffix
    postgres = containers["postgres"]
    with backup.open("wb") as output:
        subprocess.run(["docker", "exec", postgres, "pg_dump", "-U", "circular_admin", "-d", "circular", "-Fc"], cwd=ROOT, stdout=output, stderr=subprocess.PIPE, check=True)
    command("docker", "exec", postgres, "createdb", "-U", "circular_admin", "-O", "circular_app", database)
    try:
        with backup.open("rb") as source:
            subprocess.run(["docker", "exec", "-i", postgres, "pg_restore", "-U", "circular_admin", "--no-owner", "--role=circular_app", "--exit-on-error", "-d", database], cwd=ROOT, stdin=source, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        check = f"SELECT (SELECT COUNT(*) FROM users), (SELECT COUNT(*) FROM projects), (SELECT status FROM issues WHERE id={ticket['id']}), (SELECT body FROM comments WHERE id={comment['id']});"
        original = command("docker", "exec", postgres, "psql", "-U", "circular_admin", "-d", "circular", "-Atc", check)
        restored = command("docker", "exec", postgres, "psql", "-U", "circular_admin", "-d", database, "-Atc", check)
        assert original == restored
    finally:
        # Only this run's generated database and exact generated backup file.
        command("docker", "exec", postgres, "dropdb", "-U", "circular_admin", database)
        backup.unlink()
    alice.call("DELETE", f'/api/projects/{project["id"]}/members/{users[1]["id"]}', expected=204)
    bob.call("GET", f'/api/issues/{ticket["id"]}', expected=404)
    alice.call("DELETE", f'/api/issues/{ticket["id"]}', expected=204)
    alice.call("DELETE", f'/api/projects/{project["id"]}', expected=204)
    command(*compose, "restart", "app")
    ready(args.url)
    alice.call("GET", f'/api/issues/{ticket["id"]}', expected=404)
    assert alice.call("GET", "/api/projects") == []
    print(json.dumps({"httpCollaboration": "passed", "restartPersistence": "passed", "backupRestore": "passed", "revocationAndDeletion": "passed", "accountsCreated": 2}))


if __name__ == "__main__":
    main()
