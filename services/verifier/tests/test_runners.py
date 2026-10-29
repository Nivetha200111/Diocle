import sys

from diocle_verifier.runners import _exec


def test_stdout_is_decoded_byte_for_byte_not_as_utf8_text():
    code = "import sys; sys.stdout.buffer.write(b'A\\xff\\rB\\r\\nC')"
    proc = _exec([sys.executable, "-c", code])
    assert proc.stdout == "A\xff\rB\r\nC"  # no UnicodeDecodeError, lone CR and CRLF both kept as they were written


def test_stdin_is_closed():
    proc = _exec([sys.executable, "-c", "import sys; print(repr(sys.stdin.read()))"])
    assert proc.stdout.strip() == "''"
