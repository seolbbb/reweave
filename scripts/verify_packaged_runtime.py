"""Exercise both Windows executables with synthetic data and a loopback-only fake provider."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import subprocess
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "For Package verification, keep package verification synthetic and local."
CLAIM = "Keep package verification synthetic and local."


class SyntheticProvider(BaseHTTPRequestHandler):
    calls = 0

    def log_message(self, *args):
        pass

    def do_POST(self):
        type(self).calls += 1
        if self.path != "/v1/chat/completions" or type(self).calls > 4:
            self.send_error(400)
            return
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert request["model"] == "synthetic-package-model"
        response = {
            "brief": {
                "main_subject": "Package verification",
                "user_goal": "Verify local behavior",
                "important_outcomes": [CLAIM],
                "decisions": [CLAIM],
                "lessons": [],
                "unresolved_questions": [],
                "actions": [],
            },
            "items": [
                {
                    "canonical_text": CLAIM,
                    "type": "decision",
                    "epistemic_kind": "observed",
                    "confidence": 0.99,
                    "sensitivity": "normal",
                    "scopes": [
                        {"type": "project", "key": "Package verification", "confidence": 0.99}
                    ],
                    "evidence": [
                        {"message_index": 0, "excerpt": SOURCE, "relationship": "supports"}
                    ],
                }
            ],
        }
        body = json.dumps({"choices": [{"message": {"content": json.dumps(response)}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def wait_until(operation, predicate, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = operation()
        if predicate(value):
            return value
        time.sleep(0.05)
    raise AssertionError("The synthetic package check exceeded its deadline.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=ROOT / "dist/Reweave")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    data = args.data_dir.resolve()
    if not data.is_relative_to(ROOT / ".pytest_cache") or data.exists():
        parser.error("Use a new, unoccupied directory below this worktree's .pytest_cache.")
    bundle = args.bundle.resolve()
    executable = bundle / "Reweave.exe"
    host = bundle / "ReweaveNativeHost.exe"
    if not executable.is_file() or not host.is_file():
        parser.error("Both freshly built executables are required.")
    data.mkdir(parents=True)
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(
            ("REWEAVE_", "OPENAI_", "ANTHROPIC_", "GEMINI_", "GOOGLE_API", "OPENROUTER_", "KIMI_")
        )
    }
    env.update(
        REWEAVE_DATA_DIR=str(data),
        REWEAVE_CREDENTIAL_BACKEND="memory",
        PYTHON_DOTENV_DISABLED="1",
        NO_PROXY="127.0.0.1,localhost",
    )
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    report = {
        "date": datetime.now(UTC).isoformat(),
        "synthetic_only": True,
        "native_windows_opened": False,
        "registered_native_hosts": False,
        "executables": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (executable, host)
        },
    }

    def native(kind, **fields):
        payload = json.dumps({"protocol_version": 1, "type": kind, **fields}).encode()
        run = subprocess.run(
            [str(host)],
            input=struct.pack("=I", len(payload)) + payload,
            capture_output=True,
            timeout=15,
            env=env,
            creationflags=flags,
        )
        assert run.returncode == 0 and len(run.stdout) >= 4
        length = struct.unpack("=I", run.stdout[:4])[0]
        assert len(run.stdout) == length + 4 and not run.stderr
        response = json.loads(run.stdout[4:])
        assert "token" not in response and "port" not in response
        return response

    @contextmanager
    def runtime():
        stop = data / "stop-request"
        stop.unlink(missing_ok=True)
        process = subprocess.Popen(
            [
                str(executable),
                "--headless",
                "--data-dir",
                str(data),
                "--run-for",
                "180",
                "--stop-file",
                str(stop),
            ],
            env=env,
            creationflags=flags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        descriptor = data / "extension-bridge.json"
        try:
            wait_until(lambda: descriptor.exists() or process.poll() is not None, bool)
            assert process.poll() is None and descriptor.exists(), "Packaged startup failed."
            metadata = json.loads(descriptor.read_text(encoding="utf-8"))
            with httpx.Client(
                base_url=f"http://127.0.0.1:{metadata['port']}", trust_env=False, timeout=30
            ) as client:
                assert client.get("/api/health").json()["status"] == "ok"
                assert client.get("/").status_code == 200
                yield client
        finally:
            stop.touch()
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=10)
                raise AssertionError("Owned packaged process did not stop normally.") from None
            assert process.returncode == 0
            assert not descriptor.exists(), "Runtime descriptor survived owned shutdown."

    capture = {
        "provider": "chatgpt",
        "external_id": "synthetic-package-source",
        "title": "Package verification",
        "created_at": "2026-09-10T00:00:00Z",
        "messages": [
            {"external_id": "turn-0", "role": "user", "content": SOURCE},
            {"external_id": "turn-1", "role": "assistant", "content": "Agreed."},
        ],
    }
    request = {
        "provider": "chatgpt",
        "external_id": "12345678-1234-4234-8234-123456789abc",
        "messages": [
            {"role": "user", "content": "Package verification"},
            {"role": "assistant", "content": "Continue the check."},
        ],
        "draft": "Apply the package verification decision. UNSAVED-DRAFT-SENTINEL-4198",
        "max_context_chars": 6000,
    }
    provider = ThreadingHTTPServer(("127.0.0.1", 0), SyntheticProvider)
    thread = threading.Thread(target=provider.serve_forever, daemon=True)
    thread.start()
    try:
        with runtime() as client:
            assert native("ping")["status"] == "ready"
            saved = native("capture_conversation", capture=capture)
            assert saved["status"] == "saved", saved
            queue = client.get("/api/context/analysis/queue").json()["results"]
            assert len(queue) == 1 and queue[0]["status"] == "pending"
            job = queue[0]
            assert (
                client.post(
                    f"/api/context/analysis/queue/{job['id']}/retry",
                    json={
                        "settings": {
                            "provider": "openai-compatible",
                            "model": "synthetic-package-model",
                            "api_key": "synthetic-local-only",
                            "base_url": f"http://127.0.0.1:{provider.server_port}/v1",
                        },
                    },
                ).status_code
                == 202
            )
            done = wait_until(
                lambda: client.get(f"/api/context/analysis/queue/{job['id']}").json(),
                lambda row: row["status"] in {"complete", "failed"},
            )
            assert done["status"] == "complete", done
            items = client.get("/api/context/items").json()["results"]
            assert len(items) == 1 and items[0]["canonical_text"] == CLAIM
            assert items[0]["evidence"][0]["excerpt"] == SOURCE
            assert native("assemble_context", context_request=request)["status"] == (
                "destination_confirmation_required"
            )
            destination = {
                **request,
                "action": "save_destination",
                "destination": "private",
                "allowed_space_ids": [],
                "expected_revision": 0,
            }
            assert (
                native("assemble_context", context_request=destination)["status"]
                == "destination_saved"
            )
            used = native("assemble_context", context_request=request)
            assert used["status"] == "ready" and CLAIM in used["insertion_text"], used
            report.update(
                capture=True,
                queued_without_key=True,
                analyzed=True,
                exact_source_evidence=True,
                native_use=True,
                source_segments=done["coverage"]["total_segments"],
            )
        with runtime() as client:
            assert client.get("/api/context/items").json()["results"] == items
            assert native("assemble_context", context_request=request)["status"] == "ready"
            repeated = native("capture_conversation", capture=capture)
            assert repeated["outcome"] == "unchanged", repeated
            assert len(client.get("/api/context/analysis/queue").json()["results"]) == 1
            report.update(
                restart_persistence=True, repeat_save_idempotent=True, destination_persisted=True
            )
        assert b"UNSAVED-DRAFT-SENTINEL-4198" not in (data / "reweave.db").read_bytes()
        assert b"synthetic-local-only" not in (data / "reweave.db").read_bytes()
        assert native("ping")["status"] == "unavailable"
        report.update(
            transient_draft_not_stored=True,
            descriptor_cleanup=True,
            loopback_fake_provider_calls=SyntheticProvider.calls,
            paid_provider_calls=0,
            outcome="passed",
        )
    finally:
        provider.shutdown()
        provider.server_close()
        thread.join(timeout=5)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
