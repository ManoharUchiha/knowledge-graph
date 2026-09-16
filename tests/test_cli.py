import os
import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock

from repo_intelligence.cli.main import cli
from repo_intelligence.graph.client import Neo4jClient


@pytest.fixture
def runner():
    return CliRunner()


def test_cli_index(runner, tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "main.py").write_text("def main():\n    pass")

    with patch("repo_intelligence.cli.main.Neo4jClient") as mock_client_cls:
        mock_client = MagicMock(spec=Neo4jClient)
        mock_client_cls.return_value = mock_client
        result = runner.invoke(cli, ["index", str(repo_dir)])

    assert result.exit_code == 0, result.output
    assert "Found 1 files" in result.output
    assert mock_client.execute_query.called
