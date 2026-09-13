import shutil
from pathlib import Path

import pytest

from gedcom_mcp.gedcom.file import GedcomFile

FIXTURE = Path(__file__).parent / "fixtures" / "sample.ged"


@pytest.fixture
def fixture_bytes() -> bytes:
    return FIXTURE.read_bytes()


@pytest.fixture
def ged_dir(tmp_path: Path) -> Path:
    """A scratch directory holding a copy of the sample file as ``smith.ged``."""
    shutil.copy(FIXTURE, tmp_path / "smith.ged")
    return tmp_path


@pytest.fixture
def ged(ged_dir: Path) -> GedcomFile:
    return GedcomFile.load(ged_dir / "smith.ged")
