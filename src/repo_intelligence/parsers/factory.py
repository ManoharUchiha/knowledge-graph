from typing import Dict, Type
from repo_intelligence.parsers.base import BaseParser, ParserContext
from repo_intelligence.parsers.python import PythonParser
from repo_intelligence.parsers.yaml import YamlParser
from repo_intelligence.parsers.terraform import TerraformParser
from repo_intelligence.parsers.go import GoParser


class ParserFactory:
    _parsers: Dict[str, Type[BaseParser]] = {
        "python": PythonParser,
        "yaml": YamlParser,
        "hcl": TerraformParser,
        "go": GoParser,
    }

    @classmethod
    def supports(cls, language: str) -> bool:
        return language in cls._parsers

    @classmethod
    def get_parser(cls, language: str, context: ParserContext) -> BaseParser:
        parser_class = cls._parsers.get(language)
        if not parser_class:
            raise ValueError(f"Unsupported language: {language}")
        return parser_class(context)
