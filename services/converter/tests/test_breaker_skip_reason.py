from diocle_converter.__main__ import _no_single_file


def test_display_only_says_no_output_file_not_no_input_file():
    reason = _no_single_file({"displayOnly": True})
    assert "writes no output file" in reason and "reads no input" not in reason


def test_other_programs_without_layouts_do_not_claim_several_files():
    assert "not have exactly one of each" in _no_single_file({})
