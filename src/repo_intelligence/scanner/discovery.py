import os
from typing import List
from repo_intelligence.config import EXTENSION_TO_LANGUAGE, Config
from repo_intelligence.models.core import FileInfo


class RepositoryScanner:
    def __init__(self, config: Config):
        self.config = config

    def scan(self) -> List[FileInfo]:
        found_files = []
        root_path = self.config.repo_path

        for root, dirs, files in os.walk(root_path):
            # Modify dirs in-place to skip ignored directories
            dirs[:] = [d for d in dirs if d not in self.config.ignore_dirs]

            for file in files:
                file_path = os.path.join(root, file)
                # Get relative path for consistency
                rel_path = os.path.relpath(file_path, root_path)

                _, ext = os.path.splitext(file)
                language = EXTENSION_TO_LANGUAGE.get(ext.lower())

                if language:
                    try:
                        size = os.path.getsize(file_path)
                        found_files.append(FileInfo(path=rel_path, language=language, size=size))
                    except OSError:
                        # Handle cases where file might be deleted or inaccessible
                        continue

        return found_files
