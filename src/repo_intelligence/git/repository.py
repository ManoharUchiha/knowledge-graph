import os
import subprocess
from dataclasses import dataclass
from typing import Optional


@dataclass
class GitInfo:
    repo_name: str
    root_path: str
    branch: str
    commit: str
    dirty: bool


class GitRepository:
    def __init__(self, repo_path: str):
        self.repo_path = repo_path

    def _run(self, cmd: list[str]) -> str:
        try:
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return ""

    def get_info(self) -> GitInfo:
        root = self._run(["git", "rev-parse", "--show-toplevel"])
        if not root:
            root = os.path.abspath(self.repo_path)

        commit = self._run(["git", "rev-parse", "HEAD"])
        if not commit:
            commit = "unknown"

        branch = self._run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        if not branch:
            branch = "unknown"

        dirty = bool(self._run(["git", "status", "--porcelain"]))

        repo_name = os.path.basename(root.rstrip(os.sep))

        return GitInfo(
            repo_name=repo_name,
            root_path=root,
            branch=branch,
            commit=commit,
            dirty=dirty,
        )
