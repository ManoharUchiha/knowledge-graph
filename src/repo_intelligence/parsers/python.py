from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Any
import tree_sitter_python as tspython
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
class _ClassInfo:
    name: str
    qualified_name: str
    node: object


@dataclass
class _FunctionInfo:
    name: str
    qualified_name: str
    node: object
    parent_class: Optional[_ClassInfo] = None


@dataclass
class _ImportInfo:
    # Name bound in the local namespace (what appears at a call site).
    bound_name: str
    # Module recorded for the IMPORTS edge (target = module:<import_module>).
    import_module: str
    # Base string used to reconstruct call targets from the bound name.
    call_base: str
    node: object = None


@dataclass
class _CallInfo:
    caller_scope_id: Optional[str]
    caller_class_qname: Optional[str]
    callee_text: str
    node: object


class PythonParser(BaseParser):
    def __init__(self, context):
        super().__init__(Language(tspython.language()), context)

    def parse(self, file_path: str, source_code: bytes) -> Tuple[List[Symbol], List[Relationship]]:
        tree = self.parser.parse(source_code)
        root_node = tree.root_node

        # Package of the file being parsed, used to resolve relative imports.
        self._current_package = self._package_from_file(file_path)

        classes: List[_ClassInfo] = []
        functions: List[_FunctionInfo] = []
        imports: List[_ImportInfo] = []
        calls: List[_CallInfo] = []

        class_stack: List[_ClassInfo] = []
        function_stack: List[_FunctionInfo] = []

        self._walk(
            root_node,
            source_code,
            file_path,
            classes,
            functions,
            imports,
            calls,
            class_stack,
            function_stack,
        )

        symbols: List[Symbol] = []
        relationships: List[Relationship] = []
        file_id = self._make_file_id(file_path)

        # Build maps of names to symbol IDs for in-file resolution.
        # local_defs: short name -> symbol id (last definition wins on collision).
        # qualified_defs: fully-qualified name (e.g. "C.method") -> symbol id.
        local_defs: Dict[str, str] = {}
        qualified_defs: Dict[str, str] = {}
        for cls in classes:
            symbol_id = self._make_symbol_id(file_path, cls.qualified_name)
            local_defs[cls.name] = symbol_id
            qualified_defs[cls.qualified_name] = symbol_id
        for fn in functions:
            symbol_id = self._make_symbol_id(file_path, fn.qualified_name)
            local_defs[fn.name] = symbol_id
            qualified_defs[fn.qualified_name] = symbol_id

        # Build import maps.
        # base_modules: imported module -> node (one IMPORTS edge per module).
        # call_resolution: local bound name -> base string for call reconstruction.
        base_modules: Dict[str, Any] = {}
        call_resolution: Dict[str, str] = {}

        for imp in imports:
            base_modules.setdefault(imp.import_module, imp.node)
            call_resolution[imp.bound_name] = imp.call_base

        # Create one module symbol per base module and IMPORTS relationship.
        for module_path, node in base_modules.items():
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

        # Class symbols
        for cls in classes:
            symbol_id = self._make_symbol_id(file_path, cls.qualified_name)
            symbols.append(
                Symbol(
                    id=symbol_id,
                    repo=self.context.repo_name,
                    branch=self.context.branch,
                    commit=self.context.commit,
                    name=cls.name,
                    symbol_type=SymbolType.CLASS,
                    location=self._create_location(cls.node, file_path),
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
                    evidence=[self._evidence(cls.node, file_path)],
                )
            )

        # Function / method symbols
        for fn in functions:
            symbol_id = self._make_symbol_id(file_path, fn.qualified_name)
            symbol_type = SymbolType.METHOD if fn.parent_class else SymbolType.FUNCTION
            parent_id = (
                self._make_symbol_id(file_path, fn.parent_class.qualified_name)
                if fn.parent_class
                else None
            )
            symbols.append(
                Symbol(
                    id=symbol_id,
                    repo=self.context.repo_name,
                    branch=self.context.branch,
                    commit=self.context.commit,
                    name=fn.name,
                    symbol_type=symbol_type,
                    location=self._create_location(fn.node, file_path),
                    parent_id=parent_id,
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
            if parent_id:
                relationships.append(
                    Relationship(
                        source_id=parent_id,
                        target_id=symbol_id,
                        rel_type=RelationType.DEFINES,
                        repo=self.context.repo_name,
                        branch=self.context.branch,
                        commit=self.context.commit,
                        evidence=[self._evidence(fn.node, file_path)],
                    )
                )

        # Call relationships
        for call in calls:
            caller_id = call.caller_scope_id or file_id
            callee_target = self._resolve_name(
                call.callee_text, local_defs, call_resolution, qualified_defs, call.caller_class_qname
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

        # Class inheritance
        for cls in classes:
            class_symbol_id = self._make_symbol_id(file_path, cls.qualified_name)
            self._extract_class_bases(
                cls, source_code, file_path, class_symbol_id, relationships, local_defs, call_resolution, qualified_defs
            )

        return symbols, relationships

    def _extract_class_bases(
        self,
        cls: _ClassInfo,
        source_code: bytes,
        file_path: str,
        class_symbol_id: str,
        relationships: List[Relationship],
        local_defs: Dict[str, str],
        import_map: Dict[str, str],
        qualified_defs: Dict[str, str],
    ):
        """Extract INHERITS relationships from a class definition's base classes.

        Base classes are resolved through the same name resolver used for calls,
        so a locally defined or imported base links to a concrete/module symbol
        instead of always producing an ``unresolved:`` target.
        """
        argument_list = None
        for child in cls.node.children:
            if child.type == "argument_list":
                argument_list = child
                break
        if not argument_list:
            return

        for base_node in argument_list.children:
            if base_node.type in ("(", ")", ","):
                continue
            base_text = self._get_node_text(base_node, source_code).strip()
            if not base_text:
                continue
            target = self._resolve_name(base_text, local_defs, import_map, qualified_defs, None)
            relationships.append(
                Relationship(
                    source_id=class_symbol_id,
                    target_id=target,
                    rel_type=RelationType.INHERITS,
                    repo=self.context.repo_name,
                    branch=self.context.branch,
                    commit=self.context.commit,
                    confidence=0.5 if target.startswith("unresolved:") else 0.9,
                    evidence=[self._evidence(base_node, file_path)],
                    metadata={"base_name": base_text},
                )
            )

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

    def _module_symbol_id(self, module_path: str) -> str:
        # External/local module namespace; resolver may map local modules to file symbols later.
        return f"module:{module_path}"

    def _resolve_name(
        self,
        text: str,
        local_defs: Dict[str, str],
        import_map: Dict[str, str],
        qualified_defs: Dict[str, str],
        caller_class_qname: Optional[str],
    ) -> str:
        """Resolve a dotted name (call or base class) to a symbol/module id."""
        if not text:
            return "unresolved:"

        parts = text.split(".")
        head = parts[0]

        # Method access via the current instance/class: self.foo / cls.foo.
        if head in ("self", "cls") and caller_class_qname and len(parts) >= 2:
            candidates = [
                f"{caller_class_qname}." + ".".join(parts[1:]),
                f"{caller_class_qname}.{parts[1]}",
            ]
            for candidate in candidates:
                if candidate in qualified_defs:
                    return qualified_defs[candidate]
            return f"unresolved:{text}"

        # Single name: local definition or imported name.
        if len(parts) == 1:
            if head in local_defs:
                return local_defs[head]
            if head in import_map:
                return self._module_symbol_id(import_map[head])
            return f"unresolved:{head}"

        # Dotted access rooted at an import binds to that module namespace.
        if head in import_map:
            return self._module_symbol_id(".".join([import_map[head]] + parts[1:]))

        # Locally-qualified access such as LocalClass.method.
        for candidate in (text, f"{head}.{parts[1]}"):
            if candidate in qualified_defs:
                return qualified_defs[candidate]

        return f"unresolved:{text}"

    def _walk(
        self,
        node,
        source_code: bytes,
        file_path: str,
        classes: List[_ClassInfo],
        functions: List[_FunctionInfo],
        imports: List[_ImportInfo],
        calls: List[_CallInfo],
        class_stack: List[_ClassInfo],
        function_stack: List[_FunctionInfo],
    ):
        # Imports are top-level-ish; still collect anywhere they appear.
        if node.type == "import_statement":
            self._collect_import_statement(node, source_code, imports)
        elif node.type == "import_from_statement":
            self._collect_import_from_statement(node, source_code, imports)
        elif node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = self._get_node_text(name_node, source_code)
                class_qname = ".".join([c.qualified_name for c in class_stack] + [name])
                cls_info = _ClassInfo(name=name, qualified_name=class_qname, node=node)
                classes.append(cls_info)
                class_stack.append(cls_info)
                for child in node.children:
                    self._walk(
                        child,
                        source_code,
                        file_path,
                        classes,
                        functions,
                        imports,
                        calls,
                        class_stack,
                        function_stack,
                    )
                class_stack.pop()
            return
        elif node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = self._get_node_text(name_node, source_code)
                parent_class = class_stack[-1] if class_stack else None
                qname_parts = []
                if parent_class:
                    qname_parts.append(parent_class.qualified_name)
                qname_parts.append(name)
                fn_info = _FunctionInfo(
                    name=name,
                    qualified_name=".".join(qname_parts),
                    node=node,
                    parent_class=parent_class,
                )
                functions.append(fn_info)
                function_stack.append(fn_info)
                for child in node.children:
                    self._walk(
                        child,
                        source_code,
                        file_path,
                        classes,
                        functions,
                        imports,
                        calls,
                        class_stack,
                        function_stack,
                    )
                function_stack.pop()
            return
        elif node.type == "call":
            func_node = node.child_by_field_name("function")
            if func_node:
                callee_text = self._get_node_text(func_node, source_code)
                caller_scope_id = None
                caller_class_qname = None
                if function_stack:
                    caller_scope_id = self._make_symbol_id(
                        file_path, function_stack[-1].qualified_name
                    )
                    parent_class = function_stack[-1].parent_class
                    if parent_class:
                        caller_class_qname = parent_class.qualified_name
                calls.append(
                    _CallInfo(
                        caller_scope_id=caller_scope_id,
                        caller_class_qname=caller_class_qname,
                        callee_text=callee_text,
                        node=node,
                    )
                )

        for child in node.children:
            self._walk(
                child,
                source_code,
                file_path,
                classes,
                functions,
                imports,
                calls,
                class_stack,
                function_stack,
            )

    @staticmethod
    def _package_from_file(file_path: str) -> str:
        directory = os.path.dirname(file_path)
        if not directory:
            return ""
        return directory.replace(os.sep, ".").replace("/", ".")

    def _resolve_relative_package(self, level: int) -> str:
        """Ascend the current package for a relative import of the given dot count."""
        parts = [p for p in self._current_package.split(".") if p]
        ascended = parts[: len(parts) - (level - 1)] if level >= 1 else parts
        return ".".join(ascended)

    def _collect_import_statement(self, node, source_code: bytes, imports: List[_ImportInfo]):
        # `import a.b.c` | `import a.b.c as x`
        for child in node.children:
            if child.type == "dotted_name":
                module_path = self._get_node_text(child, source_code)
                # A plain dotted import binds the first component; a call like
                # a.b.c.func() reconstructs the module from that head.
                imports.append(
                    _ImportInfo(
                        bound_name=module_path.split(".")[0],
                        import_module=module_path,
                        call_base=module_path.split(".")[0],
                        node=node,
                    )
                )
            elif child.type == "aliased_import":
                name_node = child.child_by_field_name("name")
                alias_node = child.child_by_field_name("alias")
                if name_node and alias_node:
                    module_path = self._get_node_text(name_node, source_code)
                    alias = self._get_node_text(alias_node, source_code)
                    imports.append(
                        _ImportInfo(
                            bound_name=alias,
                            import_module=module_path,
                            call_base=module_path,
                            node=child,
                        )
                    )

    def _collect_import_from_statement(
        self, node, source_code: bytes, imports: List[_ImportInfo]
    ):
        # `from pkg.mod import a, b as c` and relative `from . import x` / `from .mod import y`.
        relative = next((c for c in node.children if c.type == "relative_import"), None)
        module_dotted = None
        base_package = ""
        if relative is not None:
            prefix = next((c for c in relative.children if c.type == "import_prefix"), None)
            level = self._get_node_text(prefix, source_code).count(".") if prefix else 1
            base_package = self._resolve_relative_package(level)
            module_dotted = next((c for c in relative.children if c.type == "dotted_name"), None)
        else:
            module_dotted = next((c for c in node.children if c.type == "dotted_name"), None)
            if module_dotted is None:
                return

        rel_module = self._get_node_text(module_dotted, source_code) if module_dotted is not None else ""
        if relative is not None:
            module_path = ".".join(p for p in (base_package, rel_module) if p)
            has_module = bool(rel_module)
        else:
            module_path = rel_module
            has_module = True

        # Imported names appear after the module (or after the relative_import node).
        seen_module = relative is not None or module_dotted is None
        for child in node.children:
            if child is relative or child is module_dotted:
                seen_module = True
                continue
            if not seen_module:
                continue
            if child.type == "aliased_import":
                name_node = child.child_by_field_name("name")
                alias_node = child.child_by_field_name("alias")
                if name_node:
                    name = self._get_node_text(name_node, source_code)
                    bound = self._get_node_text(alias_node, source_code) if alias_node else name
                    self._append_from_import(imports, module_path, has_module, name, bound, child)
            elif child.type in ("identifier", "dotted_name"):
                name = self._get_node_text(child, source_code)
                self._append_from_import(imports, module_path, has_module, name, name, child)

    def _append_from_import(self, imports, module_path, has_module, name, bound, node):
        if has_module:
            # `from pkg.mod import name` -> module is pkg.mod, name is a member.
            import_module = module_path
            call_base = f"{module_path}.{name}" if module_path else name
        else:
            # `from . import name` -> name is a submodule of the package.
            import_module = f"{module_path}.{name}" if module_path else name
            call_base = import_module
        imports.append(
            _ImportInfo(
                bound_name=bound,
                import_module=import_module,
                call_base=call_base,
                node=node,
            )
        )
