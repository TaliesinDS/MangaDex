import json
from pathlib import Path

import pytest
import responses


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session")
def sample_follows(fixtures_dir: Path) -> dict:
    path = fixtures_dir / "mangadex" / "sample_follows.json"
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="session")
def sample_library(fixtures_dir: Path) -> dict:
    path = fixtures_dir / "suwayomi" / "sample_library.json"
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture
def responses_mock():
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        yield rsps
