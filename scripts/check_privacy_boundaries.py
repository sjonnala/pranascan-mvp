#!/usr/bin/env python3
"""Static privacy-boundary check for PranaScan (stdlib only, runs in CI).

Rules
-----
``raw-buffer-in-sink`` (PB001)
    A logging, audit, analytics or crash-reporting call must not receive raw capture data:
    camera frames or pixel buffers, per-frame RGB/YUV traces, audio PCM or waveforms, Mel
    spectrograms, or face landmarks. Derived scalars (counts, SNR, quality scores, HR) are fine.
``fitzpatrick-without-consent`` (PB002)
    Fitzpatrick / skin-tone / ITA values may only reach a log, audit or analytics sink inside a
    branch whose condition checks consent (e.g. ``if consent.fairness_analytics:``).
``sensitive-field-in-log-model`` (PB003)
    Python classes that model audit/analytics/event/log records must not declare fields that
    hold raw capture data (PB001 vocabulary) or a Fitzpatrick class.

Scope: ``mobile/`` (``.ts``/``.tsx``/``.js``/``.jsx``) and ``service-intelligence/`` (``.py``),
skipping tests, mocks, migrations, notebooks and vendored folders. Python is parsed with
``ast``; TypeScript/JavaScript with a lexer-light scan (strings and comments are stripped,
call arguments are matched by balanced parentheses).

Suppress a reviewed false positive with a same-line or previous-line comment
``privacy-ok: <reason>`` (``#`` or ``//``). A suppression without a reason is itself a finding.

Exit code 0 when clean, 1 when there are findings, 2 on usage errors.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGETS = ("mobile", "service-intelligence")

SKIP_DIRS = frozenset(
    {
        "node_modules",
        "__tests__",
        "__mocks__",
        "tests",
        "test",
        "jest",
        "alembic",
        "notebooks",
        ".venv",
        "venv",
        ".expo",
        "build",
        "dist",
        "coverage",
        "__pycache__",
        ".git",
    }
)
PY_EXT = frozenset({".py"})
JS_EXT = frozenset({".ts", ".tsx", ".js", ".jsx"})
SKIP_FILE_RE = re.compile(r"(_pb2(_grpc)?\.py$|\.test\.[jt]sx?$|\.spec\.[jt]sx?$|\.d\.ts$)")

# ---------------------------------------------------------------- vocabulary #

LOG_METHODS = frozenset(
    {
        "debug",
        "info",
        "warning",
        "warn",
        "error",
        "exception",
        "critical",
        "log",
        "trace",
    }
)
LOGGER_OBJECTS = frozenset({"logger", "logging", "log", "_logger", "_log", "console", "LOGGER"})
SINK_NAME_RE = re.compile(
    r"(audit|analytics|telemetry|track|log_?event|capture_?(message|exception|event)"
    r"|set_?(context|extra|tag|user)|add_?breadcrumb|record_?error|posthog|mixpanel"
    r"|amplitude|segment|sentry|crashlytics|bugsnag|datadog)",
    re.IGNORECASE,
)
LOG_MODEL_CLASS_RE = re.compile(r"(Audit|Analytics|Telemetry|Event|Log)", re.ASCII)

RAW_SUBSTRINGS = ("arraybuffer", "spectrogram", "logmel", "waveform", "landmark", "pcm")
RAW_TOKENS = frozenset({"mel", "mels", "yuv", "pixels", "pixel", "stmap"})
RAW_SUBJECT = frozenset({"frame", "frames", "audio", "rgb", "image", "img", "video", "camera"})
RAW_CONTAINER = frozenset(
    {
        "buffer",
        "buffers",
        "bytes",
        "data",
        "samples",
        "frames",
        "raw",
        "array",
        "pixels",
        "trace",
    }
)
RAW_BARE = frozenset({"frames", "samples", "audio", "pcm", "frame"})
SCALAR_TOKENS = frozenset(
    {
        "n",
        "num",
        "count",
        "len",
        "length",
        "snr",
        "db",
        "ms",
        "hz",
        "rate",
        "fps",
        "ok",
        "valid",
        "quality",
        "shape",
        "size",
        "dim",
        "dims",
        "flag",
        "flags",
        "id",
        "ids",
        "type",
        "score",
        "duration",
        "dropped",
        "format",
        "encoder",
        "mime",
        "status",
        "enabled",
        "gate",
        "accepted",
        "reason",
    }
)
FITZ_RE = re.compile(r"(fitzpatrick|skin_?tone|skintone|skin_?type|phototype|\bita\b)", re.I)
CONSENT_RE = re.compile(r"consent", re.I)
SUPPRESS_RE = re.compile(r"privacy-ok\s*:?(.*)$", re.I)


@dataclass(frozen=True, order=True)
class Finding:
    path: str
    line: int
    rule: str
    message: str

    def format(self) -> str:
        return f"{self.path}:{self.line}: {self.rule} {self.message}"


def split_identifier(name: str) -> list[str]:
    """``toArrayBuffer`` -> ``['to', 'array', 'buffer']``; ``raw_frames`` -> ``['raw', 'frames']``."""
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", spaced)
    return [t for t in re.split(r"[_\W]+", spaced.lower()) if t]


def is_raw_identifier(name: str) -> bool:
    tokens = split_identifier(name)
    if not tokens or SCALAR_TOKENS.intersection(tokens):
        return False
    joined = "".join(tokens)
    if any(s in joined for s in RAW_SUBSTRINGS):
        return True
    if RAW_TOKENS.intersection(tokens):
        return True
    if len(tokens) == 1 and tokens[0] in RAW_BARE:
        return True
    return bool(RAW_SUBJECT.intersection(tokens) and RAW_CONTAINER.intersection(tokens)) and (
        len(set(tokens)) > 1
    )


def suppression(lines: Sequence[str], lineno: int) -> tuple[bool, bool]:
    """Return ``(suppressed, missing_reason)`` for a 1-based line number."""
    for idx in (lineno - 1, lineno - 2):
        if 0 <= idx < len(lines):
            m = SUPPRESS_RE.search(lines[idx])
            if m:
                reason = m.group(1).strip(" -:#/*")
                return True, not reason
    return False, False


# -------------------------------------------------------------------- Python #


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        return _dotted(node.func)
    return ""


def _is_py_sink(func: ast.AST) -> bool:
    name = _dotted(func)
    if not name:
        return False
    parts = name.split(".")
    if len(parts) >= 2 and parts[-1] in LOG_METHODS and parts[-2] in LOGGER_OBJECTS:
        return True
    if name == "AuditLog" or parts[-1] == "AuditLog":
        return True
    return bool(SINK_NAME_RE.search(parts[-1]))


def _py_arg_names(call: ast.Call) -> Iterator[tuple[str, int]]:
    """Identifiers reaching a call's arguments, skipping ``len(...)`` and ``.shape``/``.size``."""
    stack: list[ast.AST] = [*call.args, *(kw.value for kw in call.keywords)]
    for kw in call.keywords:
        if kw.arg:
            yield kw.arg, call.lineno
    while stack:
        node = stack.pop()
        if isinstance(node, ast.Call) and _dotted(node.func) in {
            "len",
            "np.size",
            "numpy.size",
        }:
            continue
        if isinstance(node, ast.Attribute) and node.attr in {
            "shape",
            "size",
            "ndim",
            "dtype",
        }:
            continue
        if isinstance(node, ast.Name):
            yield node.id, getattr(node, "lineno", call.lineno)
        elif isinstance(node, ast.Attribute):
            yield node.attr, getattr(node, "lineno", call.lineno)
            stack.append(node.value)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            continue
        else:
            stack.extend(ast.iter_child_nodes(node))


def _py_text(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover - defensive
        return ""


def check_python(path: Path, rel: str, source: str) -> list[Finding]:
    try:
        tree = ast.parse(source, filename=rel)
    except SyntaxError as exc:
        return [Finding(rel, exc.lineno or 1, "PB000", f"could not parse: {exc.msg}")]
    lines = source.splitlines()
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    def under_consent(node: ast.AST) -> bool:
        cur = parents.get(node)
        while cur is not None:
            if isinstance(cur, ast.If | ast.IfExp | ast.While) and CONSENT_RE.search(
                _py_text(cur.test)
            ):
                return True
            cur = parents.get(cur)
        return False

    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_py_sink(node.func):
            sink = _dotted(node.func)
            for name, _line in _py_arg_names(node):
                if is_raw_identifier(name):
                    findings.append(
                        Finding(
                            rel,
                            node.lineno,
                            "PB001",
                            f"raw capture data '{name}' -> {sink}()",
                        )
                    )
                    break
            arg_text = " ".join(_py_text(a) for a in [*node.args, *node.keywords])
            if FITZ_RE.search(arg_text) and not under_consent(node):
                findings.append(
                    Finding(
                        rel,
                        node.lineno,
                        "PB002",
                        f"Fitzpatrick/skin-tone value -> {sink}() outside a consent check",
                    )
                )
        elif isinstance(node, ast.ClassDef) and LOG_MODEL_CLASS_RE.search(node.name):
            for stmt in node.body:
                targets: list[ast.AST] = []
                if isinstance(stmt, ast.AnnAssign):
                    targets = [stmt.target]
                elif isinstance(stmt, ast.Assign):
                    targets = list(stmt.targets)
                for tgt in targets:
                    if not isinstance(tgt, ast.Name):
                        continue
                    if is_raw_identifier(tgt.id) or FITZ_RE.search(tgt.id):
                        findings.append(
                            Finding(
                                rel,
                                stmt.lineno,
                                "PB003",
                                f"field '{tgt.id}' on log/audit model {node.name}",
                            )
                        )
    return _apply_suppressions(findings, lines)


# ------------------------------------------------------------ TypeScript/JS #

JS_SINK_RE = re.compile(
    r"(?<![\w$.])("
    r"console\s*\.\s*(log|info|warn|error|debug|trace)"
    r"|(logger|log|Logger)\s*\.\s*\w+"
    r"|(analytics|Analytics|telemetry|Sentry|posthog|mixpanel|amplitude|segment|bugsnag"
    r"|datadogRum|DdLogs)\s*\.\s*\w+"
    r"|crashlytics\s*\(\s*\)\s*\.\s*\w+"
    r"|(track\w*|logEvent|captureException|captureMessage|addBreadcrumb|recordError"
    r"|setUser|setContext|setExtra|audit\w*|logAudit\w*)"
    r")\s*\(",
)
JS_IDENT_RE = re.compile(r"[A-Za-z_$][\w$]*")


def strip_js(source: str) -> str:
    """Blank out comments and string/template literal contents, keeping offsets and newlines."""
    out = list(source)
    i, n = 0, len(source)

    def blank(a: int, b: int) -> None:
        for k in range(a, min(b, n)):
            if out[k] != "\n":
                out[k] = " "

    while i < n:
        c = source[i]
        nxt = source[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            j = source.find("\n", i)
            j = n if j < 0 else j
            blank(i, j)
            i = j
        elif c == "/" and nxt == "*":
            j = source.find("*/", i + 2)
            j = n if j < 0 else j + 2
            blank(i, j)
            i = j
        elif c in "'\"`":
            j = i + 1
            seg_start = j
            while j < n and source[j] != c:
                if source[j] == "\\":
                    j += 1
                elif c != "`" and source[j] == "\n":
                    break
                elif c == "`" and source.startswith("${", j):
                    blank(seg_start, j)  # keep ${...} interpolations: they are code
                    depth, j = 1, j + 2
                    while j < n and depth:
                        depth += {"{": 1, "}": -1}.get(source[j], 0)
                        j += 1
                    seg_start = j
                    continue
                j += 1
            blank(seg_start, j)
            i = j + 1
        else:
            i += 1
    return "".join(out)


def _balanced(text: str, open_idx: int) -> str:
    depth = 0
    for k in range(open_idx, len(text)):
        if text[k] == "(":
            depth += 1
        elif text[k] == ")":
            depth -= 1
            if depth == 0:
                return text[open_idx + 1 : k]
    return text[open_idx + 1 :]


def _js_args_identifiers(args: str) -> Iterable[str]:
    args = re.sub(r"\.\s*(length|byteLength|size|shape)\b", "", args)
    args = re.sub(r"\b(length|byteLength)\b", "", args)
    for m in JS_IDENT_RE.finditer(args):
        yield m.group(0)


def check_js(path: Path, rel: str, source: str) -> list[Finding]:
    stripped = strip_js(source)
    lines = source.splitlines()
    findings: list[Finding] = []
    for m in JS_SINK_RE.finditer(stripped):
        open_idx = m.end() - 1
        args = _balanced(stripped, open_idx)
        lineno = stripped.count("\n", 0, m.start()) + 1
        sink = re.sub(r"\s+", "", m.group(1))
        for ident in _js_args_identifiers(args):
            if is_raw_identifier(ident):
                findings.append(
                    Finding(rel, lineno, "PB001", f"raw capture data '{ident}' -> {sink}()")
                )
                break
        raw_args = _balanced(source, open_idx)
        if FITZ_RE.search(args) or FITZ_RE.search(raw_args):
            window = "\n".join(stripped.splitlines()[max(0, lineno - 12) : lineno])
            guarded = re.search(r"\bif\s*\([^)]*consent", window, re.I) or re.search(
                r"consent\w*\s*(&&|\?)", window, re.I
            )
            if not guarded:
                findings.append(
                    Finding(
                        rel,
                        lineno,
                        "PB002",
                        f"Fitzpatrick/skin-tone value -> {sink}() outside a consent check",
                    )
                )
    return _apply_suppressions(findings, lines)


# ------------------------------------------------------------------- driver #


def _apply_suppressions(findings: list[Finding], lines: Sequence[str]) -> list[Finding]:
    kept: list[Finding] = []
    for f in findings:
        suppressed, missing_reason = suppression(lines, f.line)
        if not suppressed:
            kept.append(f)
        elif missing_reason:
            kept.append(Finding(f.path, f.line, "PB900", "privacy-ok suppression needs a reason"))
    return kept


def iter_source_files(root: Path, targets: Sequence[str]) -> Iterator[Path]:
    for target in targets:
        base = (root / target).resolve()
        if base.is_file():
            yield base
            continue
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if not p.is_file() or p.suffix not in PY_EXT | JS_EXT:
                continue
            rel_parts = p.relative_to(base).parts[:-1]
            if any(part in SKIP_DIRS or part.startswith(".") for part in rel_parts):
                continue
            if SKIP_FILE_RE.search(p.name):
                continue
            yield p


def scan(root: Path, targets: Sequence[str] = DEFAULT_TARGETS) -> list[Finding]:
    findings: list[Finding] = []
    for path in iter_source_files(root, targets):
        try:
            rel = str(path.relative_to(root))
        except ValueError:
            rel = str(path)
        source = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix in PY_EXT:
            findings.extend(check_python(path, rel, source))
        else:
            findings.extend(check_js(path, rel, source))
    return sorted(set(findings))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("targets", nargs="*", default=list(DEFAULT_TARGETS))
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)
    if not args.root.is_dir():
        print(f"root not found: {args.root}", file=sys.stderr)
        return 2
    findings = scan(args.root.resolve(), args.targets)
    for f in findings:
        print(f.format())
    print(f"privacy-boundaries: {len(findings)} finding(s) in {', '.join(args.targets)}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
