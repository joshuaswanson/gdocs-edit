from __future__ import annotations

import json
import subprocess


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


def get_document(document_id: str) -> dict:
    return _run([
        "docs", "documents", "get",
        "--params", json.dumps({"documentId": document_id}),
    ])


def batch_update(document_id: str, requests: list[dict]) -> dict:
    return _run([
        "docs", "documents", "batchUpdate",
        "--params", json.dumps({"documentId": document_id}),
        "--json", json.dumps({"requests": requests}),
    ])
