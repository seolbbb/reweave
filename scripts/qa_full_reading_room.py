"""Run recorded agent-browser commands against the synthetic Reading Room session.

This helper never starts a real browser profile or changes product code. Supply
commands after `--`; use `--eval-file` for JS passed intact through stdin.
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "docs/verification/2026-09-10"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-file", type=Path)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--save-blob", type=Path)
    parser.add_argument("--mime", default="image/png")
    parser.add_argument("commands", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    commands = args.commands[1:] if args.commands[:1] == ["--"] else args.commands
    stdin = None
    if args.eval_file:
        commands = ["eval", "--stdin"]
        stdin = args.eval_file.read_text(encoding="utf-8")
    if args.save_blob:
        target = args.save_blob.resolve()
        if not (
            target.is_relative_to(ARTIFACTS)
            or target.is_relative_to(ROOT / ".pytest_cache/reading-room-uiqa")
        ):
            parser.error("Observed blobs must stay in the isolated QA paths.")
        commands = ["eval", "--stdin"]
        stdin = (
            "(async()=>{const b=window.qaDownloadBlobs.filter(b=>b.type==="
            + json.dumps(args.mime)
            + ").at(-1);if(!b)throw new Error('No observed Blob');"
            "const bytes=new Uint8Array(await b.arrayBuffer());let out='';"
            "for(const byte of bytes)out+=String.fromCharCode(byte);return btoa(out)})()"
        )
    base = [
        str(args.binary),
        "--config",
        str(ROOT / ".pytest_cache/reading-room-uiqa/agent-browser.json"),
        "--session",
        "reading-room-uiqa-0910",
    ]
    result = subprocess.run(
        [*base, *commands],
        input=stdin,
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=45,
        cwd=ROOT,
    )
    if args.save_blob and result.returncode == 0:
        payload = base64.b64decode(json.loads(result.stdout))
        target.write_bytes(payload)
        result.stdout = (
            json.dumps(
                {
                    "observed_blob_path": str(target.relative_to(ROOT)),
                    "bytes": len(payload),
                    "mime": args.mime,
                    "browser_download_completion": (
                        "canceled by harness, including independent control"
                    ),
                }
            )
            + "\n"
        )
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    record = {
        "time": datetime.now(UTC).isoformat(),
        "command": commands,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    if stdin:
        record["evaluation"] = stdin
    with (ARTIFACTS / "browser-qa-transcript.jsonl").open("a", encoding="utf-8") as output:
        output.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(result.stdout, end="")
    print(result.stderr, end="")
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
