#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Jenkinsfile Parser for OSCAR.

Regex-based parser that extracts parameter definitions from Groovy
declarative pipeline Jenkinsfiles. Handles any parameter type that
follows the standard Jenkins DSL pattern: typeName(name: '...', ...).
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@dataclass
class ParsedParameter:
    """A single parameter extracted from a Jenkinsfile."""
    name: str
    parameter_type: str  # "string", "boolean", "choice", "activeChoice", "reactiveChoice", etc.
    description: str = ""
    required: bool = True
    default_value: Optional[str] = None
    choices: Optional[List[str]] = None
    referenced_parameters: Optional[str] = None
    choice_map: Optional[Dict[str, List[str]]] = None


@dataclass
class ParsedJob:
    """A complete job definition extracted from a Jenkinsfile."""
    job_name: str
    description: str
    jenkinsfile_path: str
    parameters: List[ParsedParameter] = field(default_factory=list)


# Map Groovy DSL function names to a normalized type string.
_TYPE_MAP = {
    'string': 'string',
    'text': 'text',
    'booleanParam': 'boolean',
    'choice': 'choice',
    'password': 'password',
    'activeChoice': 'activeChoice',
    'reactiveChoice': 'reactiveChoice',
}


class JenkinsfileParser:
    """Regex-based parser for extracting parameter definitions from Jenkinsfiles."""

    JOB_NAME_PATTERN = re.compile(r'//\s*@job-name:\s*(.+)')
    DESCRIPTION_PATTERN = re.compile(r'//\s*@description:\s*(.+)')

    # Matches any top-level function call inside the parameters block.
    _PARAM_CALL_PATTERN = re.compile(r'\b(\w+)\s*\(')

    def parse(self, content: str, jenkinsfile_path: str = "") -> ParsedJob:
        """Parse a Jenkinsfile and return a ParsedJob.

        Args:
            content: The full Jenkinsfile content as a string.
            jenkinsfile_path: The relative path of the Jenkinsfile.

        Returns:
            A ParsedJob with extracted annotations and parameters.

        Raises:
            ValueError: If the @job-name annotation is missing.
        """
        job_name = self._extract_annotation(content, self.JOB_NAME_PATTERN)
        if not job_name:
            raise ValueError(f"No @job-name annotation found in {jenkinsfile_path}")

        description = self._extract_annotation(content, self.DESCRIPTION_PATTERN) or ""

        params_block = self._extract_parameters_block(content)
        parameters = self._parse_parameters_block(params_block) if params_block else []

        self._apply_required_rules(parameters)

        return ParsedJob(
            job_name=job_name,
            description=description,
            jenkinsfile_path=jenkinsfile_path,
            parameters=parameters,
        )

    # ------------------------------------------------------------------
    # Annotation extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_annotation(content: str, pattern: re.Pattern) -> Optional[str]:
        match = pattern.search(content)
        return match.group(1).strip() if match else None

    # ------------------------------------------------------------------
    # Parameters block extraction (brace-depth counting)
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_parameters_block(content: str) -> Optional[str]:
        match = re.search(r'\bparameters\s*\{', content)
        if not match:
            return None
        start = match.end()
        depth = 1
        pos = start
        while pos < len(content) and depth > 0:
            if content[pos] == '{':
                depth += 1
            elif content[pos] == '}':
                depth -= 1
            pos += 1
        return content[start:pos - 1]

    # ------------------------------------------------------------------
    # Generic parameter block walking
    # ------------------------------------------------------------------

    def _parse_parameters_block(self, block: str) -> List[ParsedParameter]:
        """Walk through the parameters block, find each top-level call, parse it."""
        parameters: List[ParsedParameter] = []
        pos = 0

        while pos < len(block):
            match = self._PARAM_CALL_PATTERN.search(block, pos)
            if not match:
                break

            fn_name = match.group(1)
            open_paren = match.end() - 1

            if fn_name not in _TYPE_MAP:
                pos = match.end()
                continue

            body = self._extract_paren_body(block, open_paren)
            if body is None:
                pos = match.end()
                continue

            parsed = self._parse_single_param(fn_name, body)
            if parsed:
                parameters.append(parsed)

            pos = open_paren + len(body) + 2

        return parameters

    @staticmethod
    def _extract_paren_body(text: str, open_pos: int) -> Optional[str]:
        """Extract content between matching parentheses starting at open_pos."""
        if open_pos >= len(text) or text[open_pos] != '(':
            return None
        depth = 1
        pos = open_pos + 1
        while pos < len(text) and depth > 0:
            if text[pos] == '(':
                depth += 1
            elif text[pos] == ')':
                depth -= 1
            pos += 1
        return text[open_pos + 1:pos - 1]

    # ------------------------------------------------------------------
    # Single parameter parsing (generic + type-specific enrichment)
    # ------------------------------------------------------------------

    def _parse_single_param(self, fn_name: str, body: str) -> Optional[ParsedParameter]:
        """Parse one parameter declaration body."""
        name = self._extract_property(body, 'name')
        if not name:
            return None

        param_type = _TYPE_MAP.get(fn_name, fn_name)
        description = self._extract_property(body, 'description') or ""
        default_value = self._extract_property(body, 'defaultValue')
        choices = None
        referenced_parameters = None
        choice_map = None

        # For unquoted defaultValue (e.g. booleanParam defaultValue: true)
        if default_value is None:
            raw = self._extract_raw_property(body, 'defaultValue')
            if raw is not None:
                default_value = raw.lower()

        # Type-specific enrichment
        if param_type == 'choice':
            choices = self._extract_groovy_list(body, 'choices')
            if choices and default_value is None:
                default_value = choices[0]

        elif param_type == 'activeChoice':
            choices = self._extract_return_list(body)
            if choices and default_value is None:
                default_value = choices[0]

        elif param_type == 'reactiveChoice':
            referenced_parameters = self._extract_property(body, 'referencedParameters')
            choice_map = self._extract_reactive_choice_map(body)
            if choice_map:
                seen: set = set()
                choices = []
                for values in choice_map.values():
                    for v in values:
                        if v not in seen:
                            choices.append(v)
                            seen.add(v)
            if choices and default_value is None:
                default_value = choices[0]

        return ParsedParameter(
            name=name,
            parameter_type=param_type,
            description=description,
            default_value=default_value,
            choices=choices,
            referenced_parameters=referenced_parameters,
            choice_map=choice_map,
        )

    # ------------------------------------------------------------------
    # Property extraction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_property(body: str, prop_name: str) -> Optional[str]:
        """Extract a quoted string property: name: 'value' or name: \"value\"."""
        pattern = re.compile(
            rf"""{prop_name}\s*:\s*(?:'([^']*)'|"([^"]*)")""",
            re.DOTALL,
        )
        match = pattern.search(body)
        if match:
            return match.group(1) if match.group(1) is not None else match.group(2)
        return None

    @staticmethod
    def _extract_raw_property(body: str, prop_name: str) -> Optional[str]:
        """Extract an unquoted property: defaultValue: true."""
        pattern = re.compile(rf'{prop_name}\s*:\s*([^,\)\s]+)')
        match = pattern.search(body)
        return match.group(1).strip() if match else None

    @staticmethod
    def _extract_groovy_list(body: str, prop_name: str) -> List[str]:
        """Extract a Groovy list: prop: ['a', 'b', 'c']."""
        pattern = re.compile(rf"""{prop_name}\s*:\s*\[([^\]]+)\]""", re.DOTALL)
        match = pattern.search(body)
        if not match:
            return []
        return re.findall(r"""['"]([^'"]+)['"]""", match.group(1))

    @staticmethod
    def _extract_return_list(body: str) -> List[str]:
        """Extract items from a Groovy `return [...]` statement.

        When multiple return statements exist (e.g. fallbackScript + script),
        returns the list with the most items (the main script).
        """
        pattern = re.compile(r"""return\s*\[([^\]]+)\]""", re.DOTALL)
        best: List[str] = []
        for match in pattern.finditer(body):
            items = re.findall(r"""['"]([^'"]+)['"]""", match.group(1))
            if len(items) > len(best):
                best = items
        return best

    @staticmethod
    def _extract_reactive_choice_map(body: str) -> Dict[str, List[str]]:
        """Extract the if/else chain from a reactiveChoice script."""
        choice_map: Dict[str, List[str]] = {}
        pattern = re.compile(
            r"""(?:if|else\s+if)\s*\(\s*\w+\s*==\s*["']([^"']+)["']\s*\)\s*\{\s*return\s*\[([^\]]+)\]""",
            re.DOTALL,
        )
        for match in pattern.finditer(body):
            key = match.group(1)
            values = re.findall(r"""['"]([^'"]+)['"]""", match.group(2))
            if values:
                choice_map[key] = values
        return choice_map

    # ------------------------------------------------------------------
    # Required / optional detection (description-based + defaultValue)
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_required_rules(parameters: List[ParsedParameter]) -> None:
        """Determine required/optional from description text and defaultValue.

        Case-insensitive check. Handles formats like "Required:", "<Required>",
        "Optional:", "<Optional>". Rules in priority order:
        1. Description contains "required" tag/prefix -> required
        2. Description contains "optional" tag/prefix -> optional
        3. Has a defaultValue -> optional
        4. No indicator and no default -> required (conservative)
        """
        for p in parameters:
            # Strip angle brackets and whitespace: handles "Required:", "<Required>", etc.
            desc_lower = p.description.lower().strip().replace('<', '').replace('>', '').strip()
            if desc_lower.startswith("conditionally-required") or desc_lower.startswith("conditionally required"):
                p.required = False
            elif desc_lower.startswith("required"):
                p.required = True
            elif desc_lower.startswith("optional"):
                p.required = False
            elif p.default_value is not None:
                p.required = False
            else:
                p.required = True
