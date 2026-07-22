from __future__ import annotations

import pytest


def test_synthetic_timing_fixture_is_byte_deterministic(tmp_path):
    pytest.importorskip("av")
    pytest.importorskip("numpy")
    from scripts.prepare_v1_m2c_timing_fixture import build_fixture

    first = tmp_path / "first.avi"
    second = tmp_path / "second.avi"

    build_fixture(first)
    build_fixture(second)

    assert first.read_bytes() == second.read_bytes()
    assert first.read_bytes().startswith(b"RIFF")
