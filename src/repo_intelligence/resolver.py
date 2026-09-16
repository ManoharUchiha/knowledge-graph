import os
from typing import Dict
from repo_intelligence.models.core import RepositoryModel, SymbolType, Relationship


def _module_path_from_file(file_path: str) -> str:
    """Convert a relative file path to a Python module path."""
    if file_path.endswith(".py"):
        file_path = file_path[: -len(".py")]
    return file_path.replace(os.sep, ".").replace("/", ".")


def resolve_relationships(model: RepositoryModel) -> RepositoryModel:
    """Resolve symbolic target IDs to concrete symbol IDs where possible.

    Handles Python ``module:`` targets and Terraform ``tfaddr:`` references,
    mapping them onto concrete symbols defined anywhere in the model.
    """
    module_map: Dict[str, str] = {}
    tf_address_map: Dict[str, str] = {}

    for symbol in model.symbols:
        module_path = _module_path_from_file(symbol.location.file_path)
        # Map the module itself to the file symbol, if one exists.
        if symbol.symbol_type == SymbolType.FILE:
            module_map[module_path] = symbol.id
        elif symbol.symbol_type in (SymbolType.FUNCTION, SymbolType.METHOD, SymbolType.CLASS):
            qualified_name = symbol.id.split(":")[-1]
            key = f"{module_path}.{qualified_name}"
            module_map[key] = symbol.id

        tf_address = symbol.metadata.get("tf_address")
        if tf_address:
            tf_address_map[tf_address] = symbol.id

    for rel in model.relationships:
        if rel.target_id.startswith("module:"):
            module_target = rel.target_id[len("module:") :]
            if module_target in module_map:
                rel.target_id = module_map[module_target]
                rel.confidence = 0.95
                rel.metadata["resolution_status"] = "module-resolved"
            else:
                rel.confidence = 0.5
                rel.metadata["resolution_status"] = "unresolved"
        elif rel.target_id.startswith("tfaddr:"):
            address = rel.target_id[len("tfaddr:") :]
            if address in tf_address_map:
                rel.target_id = tf_address_map[address]
                rel.confidence = 0.95
                rel.metadata["resolution_status"] = "tf-resolved"
            else:
                rel.metadata["resolution_status"] = "unresolved"
        else:
            # Already a concrete symbol ID
            rel.metadata.setdefault("resolution_status", "resolved")

    return model
