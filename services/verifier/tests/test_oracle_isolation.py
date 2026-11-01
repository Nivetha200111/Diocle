"""The converted program must not be able to see or produce the original's answer.

Each test hands the verifier a cheating "conversion" that implements nothing: it looks for the original's output
file (or the compiled original itself) next to where it runs and copies it (or runs it) to produce its own output.
Before the fix the original ran first in the same directory, so these cheats were certified. Now the Java runs
first, in its own directory, before the original's outputs or executable exist, and a file the cheat leaves where
the original will run makes verification fail closed. Hand-written Java fixtures only, no model calls.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from diocle_verifier.verify import passes, verify_sample

ROOT = Path(__file__).resolve().parents[3]
SAMPLES = ROOT / "samples"

needs_toolchain = pytest.mark.skipif(shutil.which("cobc") is None or shutil.which("javac") is None,
                                     reason="needs GnuCOBOL and a JDK")

# Runs ./original or ../original (or next to any DD file) if it exists, with the same environment, so the COBOL
# writes the "converted" output and stdout itself; otherwise copies original.out / original-<DD>.out to its own DDs;
# if it found nothing, leaves a file next to its input files (where the original will run).
CHEAT = """
import java.nio.file.*;
import java.util.*;

public class MAIN {
    public static void main(String[] args) throws Exception {
        Path cwd = Path.of("").toAbsolutePath();
        List<Path> dirs = new ArrayList<>(List.of(cwd, cwd.getParent()));
        for (var e : System.getenv().entrySet())
            if (e.getKey().startsWith("DD_")) dirs.add(Path.of(e.getValue()).toAbsolutePath().getParent());
        for (Path d : dirs) {
            Path exe = d.resolve("original");
            if (Files.isRegularFile(exe) && Files.isExecutable(exe))
                System.exit(new ProcessBuilder(exe.toString()).inheritIO().start().waitFor());
        }
        int copied = 0;
        for (Path d : dirs) {
            try (var st = Files.list(d)) {
                for (Path f : (Iterable<Path>) st::iterator) {
                    String n = f.getFileName().toString();
                    String dd = n.equals("original.out") ? "OUTDD"
                              : n.startsWith("original-") && n.endsWith(".out") ? n.substring(9, n.length() - 4) : null;
                    if (dd != null && System.getenv("DD_" + dd) != null) {
                        Files.copy(f, Path.of(System.getenv("DD_" + dd)), StandardCopyOption.REPLACE_EXISTING);
                        copied++;
                    }
                }
            }
        }
        if (copied == 0)
            for (Path d : dirs.subList(2, dirs.size()))
                if (!d.equals(cwd)) Files.writeString(d.resolve("planted.out"), "x");
        System.exit(0);
    }
}
"""


def _cheat(tmp: Path, main_class: str, out_dd: str = "NONE") -> Path:
    java = tmp / "cheat"
    java.mkdir()
    (java / f"{main_class}.java").write_text(CHEAT.replace("MAIN", main_class).replace("OUTDD", out_dd))
    return java


def _assert_not_certified_and_failed_closed(report: dict) -> None:
    assert report["runs"]["converted"]["compiled"], report["runs"]["converted"]["stderr"][-500:]
    assert not passes(report)
    stderr = report["runs"]["original"]["stderr"]
    assert not report["runs"]["original"]["compiled"] and "fails closed" in stderr and "planted.out" in stderr, stderr


@needs_toolchain
def test_single_file_java_cannot_copy_or_run_the_original(tmp_path):
    """verify.py's one-input, one-output path (the reviewer's Addfee case)."""
    report = verify_sample(SAMPLES / "addfee", _cheat(tmp_path, "Addfee", "ACCTOUT"), random_count=20)
    _assert_not_certified_and_failed_closed(report)


@needs_toolchain
def test_multi_file_java_cannot_copy_or_run_the_original(tmp_path):
    """multi.py's plain path: two inputs, two outputs (original-NEWMST.out, original-EXCOUT.out)."""
    report = verify_sample(SAMPLES / "account-match", _cheat(tmp_path, "Acctmtch"), random_count=20)
    _assert_not_certified_and_failed_closed(report)


@needs_toolchain
def test_display_only_java_cannot_run_the_original_for_its_stdout(tmp_path):
    """multi.py's stdout-only path: the answer is the original's DISPLAY text, so the cheat runs the executable."""
    report = verify_sample(SAMPLES / "display-report", _cheat(tmp_path, "Txnlist"), random_count=20)
    _assert_not_certified_and_failed_closed(report)


@needs_toolchain
def test_a_java_that_reads_nothing_and_plants_nothing_is_compared_normally(tmp_path):
    """The guard only refuses what the Java did: a wrong but well-behaved conversion still gets a normal comparison."""
    java = tmp_path / "quiet"
    java.mkdir()
    (java / "Addfee.java").write_text(
        'import java.nio.file.*;\npublic class Addfee { public static void main(String[] a) throws Exception {\n'
        '  Files.write(Path.of(System.getenv("DD_ACCTOUT")), new byte[0]); } }\n')
    report = verify_sample(SAMPLES / "addfee", java, random_count=20)
    assert report["runs"]["original"]["compiled"] and report["runs"]["converted"]["compiled"]
    assert not passes(report) and report["summary"]["failed"] > 0
