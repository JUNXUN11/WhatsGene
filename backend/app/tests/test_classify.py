"""Classification tests — thresholds from docs/blast-rules.md §6."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.classify import classify_hit  # noqa: E402


def test_strong():
    assert classify_hit(1e-10, 90.0) == "strong"
    assert classify_hit(1e-5, 70.0) == "strong"


def test_borderline_by_evalue():
    assert classify_hit(1e-3, 90.0) == "borderline"


def test_borderline_by_coverage():
    assert classify_hit(1e-10, 50.0) == "borderline"


def test_not_significant_by_evalue():
    assert classify_hit(0.5, 90.0) == "not_significant"


def test_not_significant_by_coverage():
    assert classify_hit(1e-10, 20.0) == "not_significant"


if __name__ == "__main__":
    test_strong()
    test_borderline_by_evalue()
    test_borderline_by_coverage()
    test_not_significant_by_evalue()
    test_not_significant_by_coverage()
    print("test_classify: all passed")
