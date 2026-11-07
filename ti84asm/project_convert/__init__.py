"""Tools for converting existing CEdev C and ICE projects into TIpy-asm projects.

Usage::

    from ti84asm.project_convert import cedev_to_python, convert_cedev_project

    python_code = cedev_to_python(c_source_text)
    written_files = convert_cedev_project("path/to/project", "output/folder")

From the command line: ``tipy-asm convert-project path/to/project``.
"""

from __future__ import annotations

from .cedev_convert import cedev_to_python
from .ice_convert import ice_to_python
from .project_converter import convert_cedev_project, convert_ice_project, run

__all__ = ["cedev_to_python", "ice_to_python", "convert_cedev_project", "convert_ice_project", "run"]
