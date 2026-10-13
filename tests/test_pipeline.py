import platform
from pathlib import Path

from llmledger.pipeline import check_python


def test_check_python_accepts_the_pinned_version(tmp_path):
    pin = tmp_path / ".python-version"
    pin.write_text(platform.python_version() + "\n")
    assert "as pinned" in check_python(pin)


def test_check_python_warns_about_a_different_version(tmp_path):
    pin = tmp_path / ".python-version"
    pin.write_text("3.0.0\n")
    assert check_python(pin).startswith("WARNING")


def test_req_s16_versions_are_pinned_exactly():
    assert Path(".python-version").read_text().strip().count(".") == 2
    for line in Path("requirements.txt").read_text().split():
        assert "==" in line