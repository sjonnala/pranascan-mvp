#!/usr/bin/env python3
"""Fail if service-intelligence's checked-in gRPC stubs drift from scan_intelligence.proto.

Regenerates the stubs with grpcio-tools (the version pinned in
service-intelligence/requirements-dev.txt) into a temp directory and compares them with
the checked-in files: the serialized FileDescriptorProto must match exactly, and the
generated text must be byte-identical. Run from the repo root:

    python scripts/check_proto_pb2_drift.py
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROTO_DIR = ROOT / "service-core" / "src" / "main" / "proto"
PROTO = "scan_intelligence.proto"
CHECKED_IN = ROOT / "service-intelligence"
FILES = ("scan_intelligence_pb2.py", "scan_intelligence_pb2_grpc.py")


def serialized_descriptor(text: str) -> bytes:
    match = re.search(r"AddSerializedFile\((b'.*?')\)\n", text, re.S)
    if not match:
        raise SystemExit("could not find AddSerializedFile(...) in pb2 module")
    return ast.literal_eval(match.group(1))


def main() -> int:
    with tempfile.TemporaryDirectory() as out:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "grpc_tools.protoc",
                f"-I{PROTO_DIR}",
                f"--python_out={out}",
                f"--grpc_python_out={out}",
                PROTO,
            ],
            check=True,
            cwd=PROTO_DIR,
        )
        failures = []
        for name in FILES:
            fresh = (Path(out) / name).read_text()
            current = (CHECKED_IN / name).read_text()
            if name.endswith("_pb2.py") and serialized_descriptor(
                fresh
            ) != serialized_descriptor(current):
                failures.append(f"{name}: descriptor differs from {PROTO}")
            if fresh != current:
                failures.append(f"{name}: generated text differs (regenerate and commit)")
            else:
                print(f"OK  {name} matches a fresh grpc_tools.protoc run")
    for failure in failures:
        print(f"DRIFT  {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
