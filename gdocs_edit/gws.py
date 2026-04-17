from __future__ import annotations

import json
import subprocess
import sys


class GwsError(RuntimeError):
    pass


def _strip_preamble(stdout: str) -> str:
    """Strip any non-JSON lines before the first '{' or '['.

    gws sometimes prints 'Using keyring backend: keyring' before the JSON body.
    """
    for i, ch in enumerate(stdout):
        if ch in "{[":
            return stdout[i:]
    return stdout


def _run(args: list[str]) -> dict:
    try:
        result = subprocess.run(
            ["gws", *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as e:
        raise GwsError(
            "gws CLI not found on PATH. Install the Google Workspace CLI first."
        ) from e

    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        raise GwsError(
            f"gws exited with code {result.returncode}.\nstderr: {stderr}\nstdout: {stdout}"
        )

    body = _strip_preamble(result.stdout)
    if not body.strip():
        raise GwsError(f"gws returned empty output.\nstderr: {result.stderr.strip()}")

    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        raise GwsError(f"Failed to parse gws JSON output: {e}\nOutput was:\n{body}") from e


def get_document(document_id: str, include_tabs: bool = False) -> dict:
    params: dict = {"documentId": document_id}
    if include_tabs:
        params["includeTabsContent"] = True
    return _run([
        "docs", "documents", "get",
        "--params", json.dumps(params),
    ])


def batch_update(
    document_id: str,
    requests: list[dict],
    dry_run: bool = False,
) -> dict:
    """Send a batchUpdate, or print what would be sent if dry_run=True."""
    if not requests:
        raise GwsError("batch_update called with no requests.")

    body = {"requests": requests}
    if dry_run:
        print("DRY RUN: would call docs.documents.batchUpdate with:", file=sys.stderr)
        print(f"  documentId: {document_id}", file=sys.stderr)
        print("  requests:", file=sys.stderr)
        print(json.dumps(body, indent=2))
        return {"dryRun": True, "requests": requests}

    return _run([
        "docs", "documents", "batchUpdate",
        "--params", json.dumps({"documentId": document_id}),
        "--json", json.dumps(body),
    ])
