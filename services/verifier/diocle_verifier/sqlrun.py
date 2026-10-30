"""Build and run the two sides of an EXEC SQL program against the stand-in database (see sqldb.py, sqlpre.py)."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from .runners import IBM_FLAGS, Run, _exec
from .sqlpre import SUPPORT, PrecompileError, precompile

JDBC_NAMES = ("sqlite-jdbc.jar",)


JDBC_MISSING = ("the SQLite JDBC driver is not installed on the verifier, so the EXEC SQL program cannot be tested: "
                "run scripts/fetch-sqlite-jdbc.sh (on a server: rebuild the image, which installs it), or set DIOCLE_SQLITE_JDBC")


def jdbc_jar() -> Path | None:
    """The SQLite JDBC driver (org.xerial, Apache-2.0). Baked into the sandbox image at /opt/diocle/lib; on a
    developer machine set DIOCLE_SQLITE_JDBC or put the jar in services/verifier/lib/."""
    candidates = [os.environ.get("DIOCLE_SQLITE_JDBC", ""), "/opt/diocle/lib/sqlite-jdbc.jar",
                  str(Path(__file__).resolve().parents[1] / "lib" / "sqlite-jdbc.jar")]
    return next((Path(c) for c in candidates if c and Path(c).is_file()), None)


def build_cobol_sql(source: Path, copybook_dir: Path, workdir: Path, tables: list[dict], modules: list[Path] | None = None,
                    collation: str = "ascii", timeout: int = 120) -> tuple[list[str] | None, Run | None]:
    """Precompile the EXEC SQL statements, then compile program + statement table + shim with GnuCOBOL."""
    try:
        pre = precompile(source, copybook_dir, tables)
    except PrecompileError as e:
        return None, Run(False, 1, "", f"precompile: {e}")
    src = workdir / "sqlpre"
    src.mkdir(exist_ok=True)
    (src / "program.cob").write_text(pre.cobol)
    (src / "dio_stmts.c").write_text(pre.stmt_c)
    shutil.copy2(SUPPORT / "dioshim.c", src / "dioshim.c")
    exe = workdir / "original"
    colseq = ["-fdefault-colseq=EBCDIC"] if collation == "ebcdic" else []
    build = _exec(["cobc", "-x", "-std=ibm", *IBM_FLAGS, *colseq, "-I", str(copybook_dir), "-o", str(exe),
                   str(src / "program.cob"), str(src / "dio_stmts.c"), str(src / "dioshim.c"),
                   *(str(m) for m in modules or []), "-lsqlite3"], timeout=timeout)
    if build.returncode != 0:
        return None, Run(False, build.returncode, build.stdout, build.stderr)
    return [str(exe)], None


FORBIDDEN = (r"drivermanager", r"jdbc:", r"sqlite", r"class\s*\.\s*forname", r"forname", r"\battach\b", r"\bpragma\b",
             r"\bvacuum\b", r"load_extension", r"\.db\b", r"seed\.db", r"original\.db", r"converted\.db", r"diocle_db",
             r"processbuilder", r"runtime\s*\.\s*(?:getruntime|exec)", r"system\s*\.\s*load", r"loadlibrary",
             r"methodhandle", r"serviceloader", r"getenv\b(?!\s*\()", r"classloader", r"\bgetmethod\b", r"\bsetaccessible\b", r"java\.lang\.reflect",
             r"\bdatasource\b", r"org\.sqlite")


class JavaRefused(ValueError):
    pass


def check_java_source(name: str, text: str) -> None:
    """Static check of one converted source file (every file except the verifier's own DioSql.java): the Java must reach
    the database only through DioSql. Matched case-insensitively on the text, on the text with string-literal
    concatenation joined, and with every \\u escape refused; non-ASCII characters are refused outright. A speed bump
    (a determined author can still build names at run time), backed by the sandbox and by the verifier's own checks of
    the databases afterwards."""
    if re.search(r"[^\x00-\x7f]", text) or "\\u" in text:
        raise JavaRefused(f"{name}: non-ASCII characters and unicode escapes are refused in converted SQL programs")
    joined = re.sub(r'"\s*\+\s*"', "", text)
    for m in re.finditer(r"getenv\s*\(", joined):
        rest = joined[m.end():]
        if not (re.match(r'\s*"(?:DD_[A-Za-z0-9_-]+|DIOCLE_COLLATION|DIOCLE_CLOCK)"\s*\)', rest)
                or re.match(r'\s*"DD_"\s*\+\s*[A-Za-z_][\w.]*(?:\(\))?\s*\)', rest)):
            raise JavaRefused(f"{name}: System.getenv may only name a DD_ file variable, DIOCLE_COLLATION or DIOCLE_CLOCK")
    for view in (text, joined):
        low = view.lower()
        for pattern in FORBIDDEN:
            m = re.search(pattern, low)
            if m:
                raise JavaRefused(f"{name}: '{m.group(0)}' is refused: converted programs reach the database only through "
                                  "DioSql.connect() and the java.sql statements on that connection")


def stage_java(java_dir: Path, workdir: Path) -> Path:
    """A copy of the converted sources with the verifier's own DioSql.java over any file of that name."""
    for path in sorted(java_dir.rglob("*.java")):
        if path.name != "DioSql.java":
            check_java_source(path.name, path.read_text(errors="replace"))
    dest = workdir / "java-src"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(java_dir, dest, ignore=shutil.ignore_patterns("DioSql.java"))
    shutil.copy2(SUPPORT / "DioSql.java", dest / "DioSql.java")
    return dest


def build_java_sql(java_dir: Path, main_class: str, workdir: Path) -> tuple[list[str] | None, Run | None]:
    jar = jdbc_jar()
    if jar is None:
        return None, Run(False, 1, "", JDBC_MISSING)
    try:
        src = stage_java(java_dir, workdir)
    except JavaRefused as e:
        return None, Run(False, 1, "", f"refused before running: {e}")
    classes = workdir / "classes"
    classes.mkdir(exist_ok=True)
    build = _exec(["javac", "-proc:none", "-d", str(classes), *sorted(str(p) for p in src.rglob("*.java"))])
    if build.returncode != 0:
        return None, Run(False, build.returncode, build.stdout, build.stderr)
    return ["java", "--enable-native-access=ALL-UNNAMED", "-cp", f"{classes}{os.pathsep}{jar}", main_class], None
