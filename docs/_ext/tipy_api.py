"""Sphinx directives that generate the reference from the code it describes.

The method pages come from ``ti84libs.api`` and the command pages from the real
argument parser, so the documentation cannot list something the compiler lacks.
"""

from __future__ import annotations

import os
import re

from docutils import nodes
from docutils.parsers.rst import Directive
from docutils.statemachine import StringList
from sphinx.util.nodes import nested_parse_with_titles

from ti84asm.cli import build_parser
from ti84asm.flash_ce import LIBRARY_C
from ti84libs import color, graphics, keyboard
from ti84libs.api import API, Method, flash_available

TARGET_NAMES = {"ce": "CE", "classic": "Classic", "flash": "Flash App"}


def targets_of(library: str, name: str, method: Method) -> list[str]:
    found = list(method.targets)
    if flash_available(library, name):
        found.append("flash")
    return found


def parameter_names(signature: str) -> list[str]:
    inner = signature[signature.index("(") + 1:signature.rindex(")")]
    names = []
    for part in inner.split(","):
        part = part.strip()
        if part and part != "*":
            names.append(part.split("=")[0].strip())
    return names


def flash_signature(library: str, name: str, method: Method) -> str | None:
    """Return the Flash App's signature when its parameters differ from the table's."""
    if not flash_available(library, name):
        return None
    flash = [parameter[0] for parameter in LIBRARY_C[f"ti84.{library}"][name][1]]
    if flash == parameter_names(method.signature):
        return None
    return f"{name}({', '.join(flash)})"


class _Generated(Directive):
    def render(self, lines: list[str]) -> list[nodes.Node]:
        container = nodes.container()
        self.state.nested_parse(StringList(lines, source="tipy_api"), self.content_offset, container)
        return container.children


class MethodsDirective(_Generated):
    """``.. tipy-methods:: graphics`` documents every method of one library."""

    required_arguments = 1

    def run(self) -> list[nodes.Node]:
        library = self.arguments[0]
        lines: list[str] = []
        for name, method in API[library].items():
            lines += [f".. py:function:: {method.signature}", "", f"   {method.doc}", ""]
            where = targets_of(library, name, method)
            lines += [f"   :Targets: {', '.join(TARGET_NAMES[target] for target in where)}", ""]
            other = flash_signature(library, name, method)
            if other:
                lines += [f"   :Flash App form: ``{other}``", ""]
            if method.note:
                lines += [f"   :Note: {method.note[0].upper()}{method.note[1:]}.", ""]
            if method.example:
                lines += ["   .. code-block:: python", "", f"      {method.example}", ""]
        return self.render(lines)


class MatrixDirective(_Generated):
    """``.. tipy-matrix::`` tabulates every method against every target."""

    def run(self) -> list[nodes.Node]:
        lines = [".. list-table::", "   :header-rows: 1", "   :widths: 40 20 20 20", "",
                 "   * - Method", *[f"     - {TARGET_NAMES[target]}" for target in TARGET_NAMES]]
        for library, methods in API.items():
            for name, method in methods.items():
                where = targets_of(library, name, method)
                lines.append(f"   * - :py:func:`{library}.{name}() <ti84.{library}.{name}>`")
                lines += [f"     - {'Yes' if target in where else '—'}" for target in TARGET_NAMES]
        return self.render(lines)


class ConstantsDirective(_Generated):
    """``.. tipy-constants:: graphics`` lists one library's named constants."""

    required_arguments = 1

    def run(self) -> list[nodes.Node]:
        library = self.arguments[0]
        if library == "keyboard":
            values = {("KEY_" + key if key.isdigit() else key): code for key, code in keyboard.KEYS.items()}
            heading = "Scan code"
        else:
            values = graphics.COLORS if library == "graphics" else color.CONSTANTS
            heading = "RGB565 value"
        lines = [".. list-table::", "   :header-rows: 1", "   :widths: 60 40", "",
                 "   * - Constant", f"     - {heading}"]
        for name, value in sorted(values.items(), key=lambda item: (item[1], item[0])):
            lines += [f"   * - ``{library}.{name}``", f"     - ``0x{value:04X}``"]
        return self.render(lines)


class CommandsDirective(_Generated):
    """``.. tipy-commands::`` prints each subcommand's real ``--help`` text."""

    def run(self) -> list[nodes.Node]:
        previous = os.environ.get("COLUMNS")
        os.environ["COLUMNS"] = "78"
        try:
            parser = build_parser()
            subparsers = next(action for action in parser._actions if hasattr(action, "choices") and action.choices)
            lines: list[str] = []
            summaries = {action.dest: action.help for action in subparsers._choices_actions}
            for name, command in subparsers.choices.items():
                title = f"tipy-asm {name}"
                lines += [title, "-" * len(title), "", summaries[name][0].upper() + summaries[name][1:] + ".", "",
                          ".. code-block:: text", ""]
                lines += [f"   {line}" for line in command.format_help().splitlines()]
                lines.append("")
        finally:
            if previous is None:
                del os.environ["COLUMNS"]
            else:
                os.environ["COLUMNS"] = previous
        container = nodes.section()
        container.document = self.state.document
        nested_parse_with_titles(self.state, StringList(lines, source="tipy_api"), container)
        return container.children


def setup(app):
    app.add_directive("tipy-methods", MethodsDirective)
    app.add_directive("tipy-matrix", MatrixDirective)
    app.add_directive("tipy-constants", ConstantsDirective)
    app.add_directive("tipy-commands", CommandsDirective)
    return {"parallel_read_safe": True, "parallel_write_safe": True}
