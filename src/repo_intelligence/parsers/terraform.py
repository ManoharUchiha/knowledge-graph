from __future__ import annotations
from typing import List, Tuple, Optional, Set
import tree_sitter_hcl as tshcl
from tree_sitter import Language
from repo_intelligence.parsers.base import BaseParser
from repo_intelligence.models.core import (
    Symbol,
    Relationship,
    SymbolType,
    RelationType,
    SourceLocation,
    Evidence,
)

# Reference roots that are Terraform meta-arguments, not real dependencies.
_META_ROOTS = {"self", "count", "each", "path", "terraform"}


class TerraformParser(BaseParser):
    def __init__(self, context):
        super().__init__(Language(tshcl.language()), context)

    def parse(self, file_path: str, source_code: bytes) -> Tuple[List[Symbol], List[Relationship]]:
        tree = self.parser.parse(source_code)
        root_node = tree.root_node

        symbols: List[Symbol] = []
        relationships: List[Relationship] = []
        file_id = self._make_file_id(file_path)

        self._extract_all(root_node, file_path, source_code, file_id, symbols, relationships)

        return symbols, relationships

    def _get_node_text(self, node, source_code: bytes) -> str:
        return source_code[node.start_byte:node.end_byte].decode("utf-8")

    def _create_location(self, node, file_path: str) -> SourceLocation:
        return SourceLocation(
            file_path=file_path,
            start_line=node.start_point[0] + 1,
            start_col=node.start_point[1],
            end_line=node.end_point[0] + 1,
            end_col=node.end_point[1],
        )

    def _extract_all(
        self,
        node,
        file_path: str,
        source_code: bytes,
        file_id: str,
        symbols: List[Symbol],
        relationships: List[Relationship],
    ):
        if node.type == "block":
            self._extract_block(node, file_path, source_code, file_id, symbols, relationships)

        for child in node.children:
            self._extract_all(child, file_path, source_code, file_id, symbols, relationships)

    def _extract_block(
        self,
        node,
        file_path: str,
        source_code: bytes,
        file_id: str,
        symbols: List[Symbol],
        relationships: List[Relationship],
    ):
        children = node.children
        if not children:
            return
        identifier = self._get_node_text(children[0], source_code)
        labels = [self._label_text(c, source_code) for c in children if c.type == "string_lit"]
        body = next((c for c in children if c.type == "body"), None)

        if identifier == "resource" and len(labels) >= 2:
            self._add_definition(
                node, file_path, file_id, symbols, relationships,
                key=f"tf:resource:{labels[0]}.{labels[1]}", name=labels[1],
                symbol_type=SymbolType.RESOURCE, rel=RelationType.CREATES,
                address=f"{labels[0]}.{labels[1]}",
                metadata={"tf_kind": "resource", "resource_type": labels[0]},
                body=body, source_code=source_code,
            )
        elif identifier == "data" and len(labels) >= 2:
            self._add_definition(
                node, file_path, file_id, symbols, relationships,
                key=f"tf:data:{labels[0]}.{labels[1]}", name=labels[1],
                symbol_type=SymbolType.RESOURCE, rel=RelationType.CREATES,
                address=f"data.{labels[0]}.{labels[1]}",
                metadata={"tf_kind": "data", "resource_type": labels[0]},
                body=body, source_code=source_code,
            )
        elif identifier == "variable" and labels:
            self._add_definition(
                node, file_path, file_id, symbols, relationships,
                key=f"tf:var:{labels[0]}", name=labels[0],
                symbol_type=SymbolType.VARIABLE, rel=RelationType.DEFINES,
                address=f"var.{labels[0]}",
                metadata={"tf_kind": "variable"},
                body=body, source_code=source_code,
            )
        elif identifier == "output" and labels:
            self._add_definition(
                node, file_path, file_id, symbols, relationships,
                key=f"tf:output:{labels[0]}", name=labels[0],
                symbol_type=SymbolType.VARIABLE, rel=RelationType.DEFINES,
                address=None,
                metadata={"tf_kind": "output"},
                body=body, source_code=source_code,
            )
        elif identifier == "module" and labels:
            self._add_definition(
                node, file_path, file_id, symbols, relationships,
                key=f"tf:module:{labels[0]}", name=labels[0],
                symbol_type=SymbolType.MODULE, rel=RelationType.CREATES,
                address=f"module.{labels[0]}",
                metadata={"tf_kind": "module", "source": self._attribute_value(body, "source", source_code)},
                body=body, source_code=source_code,
            )
        elif identifier == "provider" and labels:
            self._add_definition(
                node, file_path, file_id, symbols, relationships,
                key=f"tf:provider:{labels[0]}", name=labels[0],
                symbol_type=SymbolType.RESOURCE, rel=RelationType.CREATES,
                address=None,
                metadata={"tf_kind": "provider"},
                body=body, source_code=source_code,
            )
        elif identifier == "locals" and body is not None:
            for attr_name, attr_node in self._body_attributes(body, source_code):
                self._add_definition(
                    attr_node, file_path, file_id, symbols, relationships,
                    key=f"tf:local:{attr_name}", name=attr_name,
                    symbol_type=SymbolType.VARIABLE, rel=RelationType.DEFINES,
                    address=f"local.{attr_name}",
                    metadata={"tf_kind": "local"},
                    body=attr_node, source_code=source_code,
                )

    def _add_definition(
        self, node, file_path, file_id, symbols, relationships,
        key, name, symbol_type, rel, address, metadata, body, source_code,
    ):
        symbol_id = self._make_symbol_id(file_path, key)
        if address:
            metadata = {**metadata, "tf_address": address}
        symbols.append(
            Symbol(
                id=symbol_id,
                repo=self.context.repo_name,
                branch=self.context.branch,
                commit=self.context.commit,
                name=name,
                symbol_type=symbol_type,
                location=self._create_location(node, file_path),
                metadata=metadata,
            )
        )
        relationships.append(
            Relationship(
                source_id=file_id,
                target_id=symbol_id,
                rel_type=rel,
                repo=self.context.repo_name,
                branch=self.context.branch,
                commit=self.context.commit,
                evidence=[self._static_evidence(node, file_path)],
            )
        )

        # Dependency edges from interpolation references inside the block body.
        for ref_address in self._reference_addresses(body, source_code):
            if ref_address == address:
                continue
            relationships.append(
                Relationship(
                    source_id=symbol_id,
                    target_id=f"tfaddr:{ref_address}",
                    rel_type=RelationType.DEPENDS_ON,
                    repo=self.context.repo_name,
                    branch=self.context.branch,
                    commit=self.context.commit,
                    confidence=0.9,
                    evidence=[self._static_evidence(node, file_path)],
                    metadata={"reference": ref_address},
                )
            )

    def _reference_addresses(self, node, source_code: bytes) -> Set[str]:
        addresses: Set[str] = set()
        if node is None:
            return addresses

        def walk(n):
            if n.type == "variable_expr":
                path = self._reference_path(n, source_code)
                address = self._path_to_address(path)
                if address:
                    addresses.add(address)
            for c in n.children:
                walk(c)

        walk(node)
        return addresses

    def _reference_path(self, variable_expr_node, source_code: bytes) -> List[str]:
        """Build a dotted path from a variable_expr and its following get_attr siblings."""
        parent = variable_expr_node.parent
        path = [self._get_node_text(variable_expr_node, source_code)]
        if parent is None:
            return path
        siblings = parent.children
        try:
            index = siblings.index(variable_expr_node)
        except ValueError:
            return path
        for sibling in siblings[index + 1:]:
            if sibling.type != "get_attr":
                break
            ident = next((c for c in sibling.children if c.type == "identifier"), None)
            if ident is None:
                break
            path.append(self._get_node_text(ident, source_code))
        return path

    @staticmethod
    def _path_to_address(path: List[str]) -> Optional[str]:
        if not path or path[0] in _META_ROOTS:
            return None
        root = path[0]
        if root == "var" and len(path) >= 2:
            return f"var.{path[1]}"
        if root == "local" and len(path) >= 2:
            return f"local.{path[1]}"
        if root == "data" and len(path) >= 3:
            return f"data.{path[1]}.{path[2]}"
        if root == "module" and len(path) >= 2:
            return f"module.{path[1]}"
        if len(path) >= 2:
            # Resource reference: TYPE.NAME(.attr...)
            return f"{root}.{path[1]}"
        return None

    def _body_attributes(self, body_node, source_code: bytes):
        for child in body_node.children:
            if child.type == "attribute":
                ident = next((c for c in child.children if c.type == "identifier"), None)
                if ident is not None:
                    yield self._get_node_text(ident, source_code), child

    def _attribute_value(self, body_node, name: str, source_code: bytes) -> Optional[str]:
        if body_node is None:
            return None
        for attr_name, attr_node in self._body_attributes(body_node, source_code):
            if attr_name == name:
                expr = next((c for c in attr_node.children if c.type == "expression"), None)
                if expr is not None:
                    return self._strip_quotes(self._get_node_text(expr, source_code))
        return None

    def _label_text(self, string_lit_node, source_code: bytes) -> str:
        literal = next(
            (c for c in string_lit_node.children if c.type == "template_literal"), None
        )
        if literal is not None:
            return self._get_node_text(literal, source_code)
        return self._strip_quotes(self._get_node_text(string_lit_node, source_code))

    def _static_evidence(self, node, file_path: str) -> Evidence:
        return Evidence(
            type="static",
            file_path=file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            confidence=0.95,
        )

    def _strip_quotes(self, value: str) -> str:
        return value.strip('"')
