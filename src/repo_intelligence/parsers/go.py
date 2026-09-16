from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Any
import tree_sitter_go as tsgo
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


@dataclass
class _ImportInfo:
    local_name: str
    module_path: str
    node: object


@dataclass
class _TypeInfo:
    name: str
    node: object


@dataclass
class _FunctionInfo:
    name: str
    node: object
    is_method: bool = False
    receiver_type: Optional[str] = None
    parent_id: Optional[str] = None


@dataclass
class _CallInfo:
    caller_scope_id: Optional[str]
    callee_text: str
    node: object


class GoParser(BaseParser):
    def __init__(self, context):
        super().__init__(Language(tsgo.language()), context)

    def parse(self, file_path: str, source_code: bytes) -> Tuple[List[Symbol], List[Relationship]]:
        tree = self.parser.parse(source_code)
        root_node = tree.root_node

        imports: List[_ImportInfo] = []
        types: List[_TypeInfo] = []
        functions: List[_FunctionInfo] = []
        calls: List[_CallInfo] = []

        self._walk(root_node, source_code, file_path, imports, types, functions, calls, None)

        symbols: List[Symbol] = []
        relationships: List[Relationship] = []
        file_id = self._make_file_id(file_path)

        # Build local definitions map for call resolution.
        local_defs: Dict[str, str] = {}
        for t in types:
            symbol_id = self._make_symbol_id(file_path, t.name)
            local_defs[t.name] = symbol_id
        for fn in functions:
            symbol_id = self._make_symbol_id(file_path, fn.name)
            local_defs[fn.name] = symbol_id

        # Build import maps.
        import_modules: Dict[str, Any] = {}
        call_resolution: Dict[str, str] = {}
        for imp in imports:
            import_modules[imp.module_path] = imp.node
            call_resolution[imp.local_name] = imp.module_path

        # Module symbols and IMPORTS relationships.
        for module_path, node in import_modules.items():
            module_symbol_id = self._module_symbol_id(module_path)
            if not any(s.id == module_symbol_id for s in symbols):
                symbols.append(
                    Symbol(
                        id=module_symbol_id,
                        repo=self.context.repo_name,
                        branch=self.context.branch,
                        commit=self.context.commit,
                        name=module_path,
                        symbol_type=SymbolType.MODULE,
                        location=self._create_location(node, file_path),
                    )
                )
            relationships.append(
                Relationship(
                    source_id=file_id,
                    target_id=module_symbol_id,
                    rel_type=RelationType.IMPORTS,
                    repo=self.context.repo_name,
                    branch=self.context.branch,
                    commit=self.context.commit,
                    evidence=[self._evidence(node, file_path)],
                )
            )

        # Type symbols.
        for t in types:
            symbol_id = self._make_symbol_id(file_path, t.name)
            symbols.append(
                Symbol(
                    id=symbol_id,
                    repo=self.context.repo_name,
                    branch=self.context.branch,
                    commit=self.context.commit,
                    name=t.name,
                    symbol_type=SymbolType.CLASS,
                    location=self._create_location(t.node, file_path),
                )
            )
            relationships.append(
                Relationship(
                    source_id=file_id,
                    target_id=symbol_id,
                    rel_type=RelationType.DEFINES,
                    repo=self.context.repo_name,
                    branch=self.context.branch,
                    commit=self.context.commit,
                    evidence=[self._evidence(t.node, file_path)],
                )
            )

        # Function / method symbols.
        for fn in functions:
            symbol_id = self._make_symbol_id(file_path, fn.name)
            symbol_type = SymbolType.METHOD if fn.is_method else SymbolType.FUNCTION
            symbols.append(
                Symbol(
                    id=symbol_id,
                    repo=self.context.repo_name,
                    branch=self.context.branch,
                    commit=self.context.commit,
                    name=fn.name,
                    symbol_type=symbol_type,
                    location=self._create_location(fn.node, file_path),
                    parent_id=fn.parent_id,
                    metadata={"receiver_type": fn.receiver_type} if fn.receiver_type else {},
                )
            )
            relationships.append(
                Relationship(
                    source_id=file_id,
                    target_id=symbol_id,
                    rel_type=RelationType.DEFINES,
                    repo=self.context.repo_name,
                    branch=self.context.branch,
                    commit=self.context.commit,
                    evidence=[self._evidence(fn.node, file_path)],
                )
            )
            if fn.parent_id:
                relationships.append(
                    Relationship(
                        source_id=fn.parent_id,
                        target_id=symbol_id,
                        rel_type=RelationType.DEFINES,
                        repo=self.context.repo_name,
                        branch=self.context.branch,
                        commit=self.context.commit,
                        evidence=[self._evidence(fn.node, file_path)],
                    )
                )

        # Call relationships.
        function_scope_map = {
            fn.name: self._make_symbol_id(file_path, fn.name)
            for fn in functions
        }
        for call in calls:
            caller_id = call.caller_scope_id or file_id
            callee_target = self._resolve_call_target(
                call.callee_text, local_defs, call_resolution
            )
            relationships.append(
                Relationship(
                    source_id=caller_id,
                    target_id=callee_target,
                    rel_type=RelationType.CALLS,
                    repo=self.context.repo_name,
                    branch=self.context.branch,
                    commit=self.context.commit,
                    confidence=0.9 if not callee_target.startswith("unresolved:") else 0.5,
                    evidence=[self._evidence(call.node, file_path)],
                    metadata={"callee_name": call.callee_text},
                )
            )

        return symbols, relationships

    def _walk(
        self,
        node,
        source_code: bytes,
        file_path: str,
        imports: List[_ImportInfo],
        types: List[_TypeInfo],
        functions: List[_FunctionInfo],
        calls: List[_CallInfo],
        current_function: Optional[_FunctionInfo],
    ):
        if node.type == "import_declaration":
            self._collect_imports(node, source_code, imports)
            return
        if node.type == "type_declaration":
            for child in node.children:
                if child.type == "type_spec":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        name = self._get_node_text(name_node, source_code)
                        types.append(_TypeInfo(name=name, node=child))
            # Continue walking in case nested declarations exist.
        if node.type == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = self._get_node_text(name_node, source_code)
                fn_info = _FunctionInfo(name=name, node=node)
                functions.append(fn_info)
                for child in node.children:
                    self._walk(
                        child,
                        source_code,
                        file_path,
                        imports,
                        types,
                        functions,
                        calls,
                        fn_info,
                    )
            return
        if node.type == "method_declaration":
            name_node = node.child_by_field_name("name")
            receiver_node = node.child_by_field_name("receiver")
            if name_node:
                name = self._get_node_text(name_node, source_code)
                receiver_type = None
                if receiver_node:
                    receiver_type = self._extract_receiver_type(receiver_node, source_code)
                fn_info = _FunctionInfo(
                    name=name,
                    node=node,
                    is_method=True,
                    receiver_type=receiver_type,
                )
                functions.append(fn_info)
                if receiver_type:
                    # Methods are conceptually defined under their receiver type.
                    fn_info.parent_id = self._make_symbol_id(file_path, receiver_type)
                for child in node.children:
                    self._walk(
                        child,
                        source_code,
                        file_path,
                        imports,
                        types,
                        functions,
                        calls,
                        fn_info,
                    )
            return
        if node.type == "call_expression":
            func_node = node.child_by_field_name("function")
            if func_node:
                callee_text = self._get_call_text(func_node, source_code)
                caller_scope_id = None
                if current_function:
                    caller_scope_id = self._make_symbol_id(
                        file_path, current_function.name
                    )
                calls.append(
                    _CallInfo(
                        caller_scope_id=caller_scope_id,
                        callee_text=callee_text,
                        node=node,
                    )
                )

        for child in node.children:
            self._walk(
                child,
                source_code,
                file_path,
                imports,
                types,
                functions,
                calls,
                current_function,
            )

    def _collect_imports(self, node, source_code: bytes, imports: List[_ImportInfo]):
        for child in node.children:
            if child.type == "import_spec":
                path_node = child.child_by_field_name("path")
                if not path_node:
                    continue
                module_path = self._strip_quotes(self._get_node_text(path_node, source_code))
                name_node = child.child_by_field_name("name")
                if name_node:
                    local_name = self._get_node_text(name_node, source_code)
                else:
                    local_name = self._default_import_alias(module_path)
                imports.append(
                    _ImportInfo(
                        local_name=local_name,
                        module_path=module_path,
                        node=child,
                    )
                )
            elif child.type == "import_spec_list":
                for spec in child.children:
                    if spec.type == "import_spec":
                        path_node = spec.child_by_field_name("path")
                        if not path_node:
                            continue
                        module_path = self._strip_quotes(
                            self._get_node_text(path_node, source_code)
                        )
                        name_node = spec.child_by_field_name("name")
                        if name_node:
                            local_name = self._get_node_text(name_node, source_code)
                        else:
                            local_name = self._default_import_alias(module_path)
                        imports.append(
                            _ImportInfo(
                                local_name=local_name,
                                module_path=module_path,
                                node=spec,
                            )
                        )

    def _extract_receiver_type(self, receiver_node, source_code: bytes) -> Optional[str]:
        for child in receiver_node.children:
            if child.type == "parameter_declaration":
                type_node = child.child_by_field_name("type")
                if type_node:
                    return self._normalize_type_name(type_node, source_code)
        return None

    def _normalize_type_name(self, node, source_code: bytes) -> str:
        text = self._get_node_text(node, source_code).strip()
        if text.startswith("*"):
            text = text[1:]
        return text.strip()

    def _get_call_text(self, node, source_code: bytes) -> str:
        return self._get_node_text(node, source_code).strip()

    def _resolve_call_target(
        self, callee_text: str, local_defs: Dict[str, str], import_map: Dict[str, str]
    ) -> str:
        if not callee_text:
            return "unresolved:"

        parts = callee_text.split(".")
        head = parts[0]

        if len(parts) == 1:
            if head in local_defs:
                return local_defs[head]
            if head in import_map:
                return self._module_symbol_id(import_map[head])
            return f"unresolved:{head}"

        if head in import_map:
            return self._module_symbol_id(".".join([import_map[head]] + parts[1:]))

        if head in local_defs:
            return f"{local_defs[head]}.{'.'.join(parts[1:])}"

        return f"unresolved:{callee_text}"

    def _module_symbol_id(self, module_path: str) -> str:
        return f"module:{module_path}"

    def _default_import_alias(self, module_path: str) -> str:
        return module_path.split("/")[-1]

    def _strip_quotes(self, value: str) -> str:
        return value.strip('"`')

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

    def _evidence(self, node, file_path: str) -> Evidence:
        return Evidence(
            type="AST",
            file_path=file_path,
            start_line=node.start_point[0] + 1,
            start_col=node.start_point[1],
            end_line=node.end_point[0] + 1,
            end_col=node.end_point[1],
            confidence=0.95,
        )
