"""Build and run the two sides of an EXEC SQL program against the stand-in database (see sqldb.py, sqlpre.py)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from .runners import IBM_FLAGS, Run, _exec
from .sqlpre import SUPPORT, PrecompileError, precompile

JDBC_NAMES = ("sqlite-jdbc.jar",)


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


def stage_java(java_dir: Path, workdir: Path) -> Path:
    """A copy of the converted sources with the verifier's own DioSql.java over any file of that name."""
    dest = workdir / "java-src"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(java_dir, dest, ignore=shutil.ignore_patterns("DioSql.java"))
    shutil.copy2(SUPPORT / "DioSql.java", dest / "DioSql.java")
    return dest


def build_java_sql(java_dir: Path, main_class: str, workdir: Path) -> tuple[list[str] | None, Run | None]:
    jar = jdbc_jar()
    if jar is None:
        return None, Run(False, 1, "", "the SQLite JDBC driver (sqlite-jdbc.jar) is not installed: set DIOCLE_SQLITE_JDBC")
    src = stage_java(java_dir, workdir)
    classes = workdir / "classes"
    classes.mkdir(exist_ok=True)
    build = _exec(["javac", "-proc:none", "-d", str(classes), *sorted(str(p) for p in src.rglob("*.java"))])
    if build.returncode != 0:
        return None, Run(False, build.returncode, build.stdout, build.stderr)
    return ["java", "--enable-native-access=ALL-UNNAMED", "-cp", f"{classes}{os.pathsep}{jar}", main_class], None
