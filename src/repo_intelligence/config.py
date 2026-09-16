import os
from typing import Set, Dict, Optional

# Directories to ignore during scanning
DEFAULT_IGNORE_DIRS: Set[str] = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    ".idea",
    ".vscode",
    "build",
    "dist",
}

# Map file extensions to language identifiers
EXTENSION_TO_LANGUAGE: Dict[str, str] = {
    ".py": "python",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".tf": "hcl",
    ".tfvars": "hcl",
    ".hcl": "hcl",
    ".go": "go",
    ".md": "markdown",
    ".json": "json",
}

class Config:
    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        self.ignore_dirs = DEFAULT_IGNORE_DIRS.copy()

    def add_ignore_dir(self, dir_name: str):
        self.ignore_dirs.add(dir_name)

# Global config instance (to be initialized by CLI)
config: Optional[Config] = None
