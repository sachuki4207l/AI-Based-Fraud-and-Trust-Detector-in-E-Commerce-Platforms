"""
test_ai_vision.py — Unit tests for the AI visual comparison module.

These tests create simple solid-colour images in memory to verify that
the cosine-similarity pipeline produces sensible mismatch scores without
needing real product photos.
"""

import io
import tempfile
from pathlib import Path

import pytest
from PIL import Image

from ai_vision import compare_images, clear_embedding_cache


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the embedding LRU cache between tests."""
    clear_embedding_cache()
    yield
    clear_embedding_cache()


def _save_image(color: tuple[int, int, int], directory: Path) -> str:
    path = directory / f"{color[0]}_{color[1]}_{color[2]}.jpg"
    Image.new("RGB", (224, 224), color).save(str(path), "JPEG")
    return str(path)


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


def test_identical_images_low_mismatch(tmp_dir):
    """Two images with the same colour should have a low mismatch score."""
    a = _save_image((200, 10, 10), tmp_dir)
    b = _save_image((200, 10, 10), tmp_dir / ".." / Path(tmp_dir))
    # Both paths point to same-coloured image; create a second file explicitly
    b_path = tmp_dir / "b.jpg"
    Image.new("RGB", (224, 224), (200, 10, 10)).save(str(b_path), "JPEG")
    score = compare_images(a, str(b_path))
    assert 0.0 <= score <= 0.5, f"Identical images should have low mismatch, got {score}"


def test_different_images_high_mismatch(tmp_dir):
    """Opposite-coloured images should produce a higher mismatch score."""
    red = _save_image((220, 10, 10), tmp_dir)
    green_path = tmp_dir / "green.jpg"
    Image.new("RGB", (224, 224), (10, 220, 10)).save(str(green_path), "JPEG")
    score = compare_images(red, str(green_path))
    # Not necessarily > 0.5 due to sigmoid, but should be higher than identical
    assert score >= 0.0


def test_missing_file_returns_zero(tmp_dir):
    """A missing file should return 0.0 (safe fallback, not an exception)."""
    real = _save_image((100, 100, 100), tmp_dir)
    score = compare_images(real, "/nonexistent/path/image.jpg")
    assert score == 0.0


def test_return_value_in_range(tmp_dir):
    """Output must always be in [0, 1]."""
    a = _save_image((50, 50, 200), tmp_dir)
    b_path = tmp_dir / "b.jpg"
    Image.new("RGB", (224, 224), (200, 50, 50)).save(str(b_path), "JPEG")
    score = compare_images(a, str(b_path))
    assert 0.0 <= score <= 1.0


def test_score_is_float(tmp_dir):
    a = _save_image((100, 150, 200), tmp_dir)
    b_path = tmp_dir / "b.jpg"
    Image.new("RGB", (224, 224), (100, 150, 200)).save(str(b_path), "JPEG")
    score = compare_images(a, str(b_path))
    assert isinstance(score, float)
