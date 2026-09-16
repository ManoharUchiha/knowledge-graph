import os
from repo_intelligence.config import Config
from repo_intelligence.scanner.discovery import RepositoryScanner


def test_scanner_discovers_files(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "main.py").write_text("def main(): pass")
    (repo_dir / "readme.md").write_text("# docs")

    config = Config(str(repo_dir))
    scanner = RepositoryScanner(config)
    files = scanner.scan()

    paths = {f.path for f in files}
    assert "main.py" in paths
    assert "readme.md" in paths


def test_scanner_ignores_directories(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    venv_dir = repo_dir / ".venv"
    venv_dir.mkdir()
    (venv_dir / "site.py").write_text("x = 1")
    (repo_dir / "app.py").write_text("def app(): pass")

    config = Config(str(repo_dir))
    scanner = RepositoryScanner(config)
    files = scanner.scan()

    paths = {f.path for f in files}
    assert "app.py" in paths
    assert all(".venv" not in f.path for f in files)


def test_scanner_skips_binaries(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "app.py").write_text("def app(): pass")
    with open(repo_dir / "image.png", "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")

    config = Config(str(repo_dir))
    scanner = RepositoryScanner(config)
    files = scanner.scan()

    paths = {f.path for f in files}
    assert "app.py" in paths
    assert "image.png" not in paths


def test_scanner_language_detection(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "main.py").write_text("x = 1")
    (repo_dir / "deploy.yml").write_text("key: value")
    (repo_dir / "main.tf").write_text('resource "x" "y" {}')

    config = Config(str(repo_dir))
    scanner = RepositoryScanner(config)
    files = {f.path: f.language for f in scanner.scan()}

    assert files["main.py"] == "python"
    assert files["deploy.yml"] == "yaml"
    assert files["main.tf"] == "hcl"
