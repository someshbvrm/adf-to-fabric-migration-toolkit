from pathlib import Path

import pytest

from adf2fabric import load_factory

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "contoso_retail"


@pytest.fixture(scope="session")
def sample_path() -> Path:
    return SAMPLE


@pytest.fixture(scope="session")
def factory():
    return load_factory(SAMPLE)
