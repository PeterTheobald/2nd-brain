import pytest


@pytest.fixture
def vault_dir(tmp_path):
    """Minimal vault structure in a temp directory."""
    (tmp_path / "ppl").mkdir()
    return tmp_path
