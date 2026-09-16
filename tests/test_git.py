import subprocess
from repo_intelligence.git.repository import GitRepository


def test_git_info(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    (repo_dir / "main.py").write_text("def main(): pass")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )

    git = GitRepository(str(repo_dir))
    info = git.get_info()

    assert info.repo_name == "repo"
    assert info.branch in ("main", "master")
    assert len(info.commit) == 40
    assert info.dirty is False
