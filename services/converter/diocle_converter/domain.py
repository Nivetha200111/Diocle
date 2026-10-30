"""EXPERIMENTAL: the customer's own record classes (POJOs) as a hint for the translator.

Only PUBLIC SIGNATURES leave this module, never bodies. Nothing here compiles, loads or runs customer code: a directory of
.java files is read as text; a .jar is read with `javap -public` (which parses class files and runs nothing). The translator
is told to shape its nested record holder after a matching class, not to call it: the verifier compiles and runs each
program alone, so verification is unchanged (the whole-repository build check, diocle_verifier.buildcheck --domain-classes,
is what compiles the programs beside the customer's classes).
"""

from __future__ import annotations

import os
import re
import subprocess
import zipfile
from pathlib import Path

from diocle_verifier.runners import safe_env

MAX_FILES, MAX_BYTES, MAX_JAR_BYTES, MAX_CLASSES, MAX_SIGNATURE = 200, 1_000_000, 20_000_000, 50, 2500
_STRIP = re.compile(r'"""(?:\\.|[^\\])*?"""|//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'', re.S)
_HEADER = re.compile(r"\bpublic\s+(?:(?:final|abstract|sealed|static)\s+)*(?:class|record|interface|enum)\s+([A-Za-z_]\w*)")


def _source_signature(text: str) -> tuple[str, str] | None:
    """(simple name, signature text) of the first public top-level type in a Java source, without any body or initializer."""
    code = _STRIP.sub(" ", text)
    flat, depth = [], 0
    for ch in code:
        if ch == "{":
            depth += 1
            if depth == 2:
                flat.append(";")  # a body at member level ends that member
            elif depth == 1:
                flat.append("{")
        elif ch == "}":
            depth = max(0, depth - 1)
            if depth == 0:
                flat.append("}")
        elif depth <= 1:
            flat.append(ch)
    flat_text = "".join(flat)
    header = _HEADER.search(flat_text)
    if not header:
        return None
    head_end = flat_text.index("{", header.start()) if "{" in flat_text[header.start():] else len(flat_text)
    lines = [re.sub(r"\s+", " ", flat_text[header.start():head_end]).strip()]
    for member in flat_text[head_end + 1:].split(";"):
        member = re.sub(r"\s+", " ", member.split("=")[0]).strip(" }{")
        if member.startswith("public "):
            lines.append(member)
    return header.group(1), "\n".join(lines)[:MAX_SIGNATURE]


def load_signatures(path: Path) -> dict[str, str]:
    """{simple class name: public signature} for a directory of .java files or a .jar. Raises ValueError for anything else."""
    path = Path(path)
    if path.is_symlink() or not path.exists():
        raise ValueError("--domain-classes must be an existing directory of .java files or a .jar (not a symlink)")
    out: dict[str, str] = {}
    if path.is_dir():
        total = count = 0
        for base, dirs, files in os.walk(path, followlinks=False):
            dirs[:] = sorted(d for d in dirs if not (Path(base) / d).is_symlink())
            for name in sorted(files):
                p = Path(base) / name
                if not name.endswith(".java") or p.is_symlink() or not p.is_file():
                    continue
                count, total = count + 1, total + p.stat().st_size
                if count > MAX_FILES or total > MAX_BYTES:
                    raise ValueError("too many or too large domain source files")
                sig = _source_signature(p.read_text(errors="replace"))
                if sig:
                    out[sig[0]] = sig[1]
        return out
    if path.suffix != ".jar" or not path.is_file() or path.stat().st_size > MAX_JAR_BYTES or not zipfile.is_zipfile(path):
        raise ValueError("--domain-classes must be an existing directory of .java files or a .jar (not a symlink)")
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
    if any(n.startswith("/") or ".." in n.split("/") for n in names):
        raise ValueError("the jar has entry names that leave the archive")
    classes = [n[:-6].replace("/", ".") for n in names if n.endswith(".class") and "$" not in n
               and not n.endswith(("module-info.class", "package-info.class"))][:MAX_CLASSES]
    for cls in classes:
        try:
            proc = subprocess.run(["javap", "-public", "-classpath", str(path), cls], capture_output=True, text=True,
                                  errors="replace", timeout=20, env=safe_env(), stdin=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            continue
        if proc.returncode == 0:
            out[cls.rsplit(".", 1)[-1]] = "\n".join(l.strip() for l in proc.stdout.splitlines()[1:] if l.strip())[:MAX_SIGNATURE]
    return out


def _norm(name: str) -> str:
    n = re.sub(r"[^A-Z0-9]", "", name.upper())
    return re.sub(r"(RECORD|REC)$", "", n) or n


def record_names(program) -> list[str]:
    """01-level record names and copybook names of a program, as the analyzer put them in its sample."""
    import json

    meta = json.loads((program.sample_dir / "sample.json").read_text())
    names = [v.get("record") for v in (meta.get("layouts") or {}).values() if isinstance(v, dict)]
    names += [Path(c).stem for c in program.copybooks]
    return [n for n in dict.fromkeys(names) if n]


def matches(program, signatures: dict[str, str]) -> dict[str, tuple[str, str]]:
    """{COBOL record or copybook name: (class name, signature)} where the names agree after dropping punctuation, case and a
    trailing REC/RECORD (CD-REC and CdRecord match)."""
    by_norm = {_norm(c): c for c in signatures}
    found = {}
    for record in record_names(program):
        cls = by_norm.get(_norm(record))
        if cls:
            found[record] = (cls, signatures[cls])
    return found


def hint(found: dict[str, tuple[str, str]]) -> str:
    """Text appended to the translator's system prompt; empty when nothing matched."""
    if not found:
        return ""
    by_class: dict[str, tuple[list[str], str]] = {}
    for record, (cls, sig) in found.items():
        by_class.setdefault(cls, ([], sig))[0].append(record)
    sigs = "\n\n".join(f"COBOL record {' / '.join(records)} <-> Java class {cls}:\n{sig}" for cls, (records, sig) in by_class.items())
    from .prompts import DOMAIN_HINT

    return DOMAIN_HINT.format(signatures=sigs)
