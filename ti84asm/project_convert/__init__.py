"""Project conversion tools for importing CEdev and ICE projects.

This package provides tools to convert existing CEdev C projects and ICE
projects into TIpy-asm Python format.

Usage:
    from ti84asm.project_convert import (
        cedev_to_python, 
        ice_to_python,
        convert_cedev_project,
        convert_ice_project,
    )
    
    # Convert a CEdev C source file
    python_code = cedev_to_python("source.c")
    
    # Convert an ICE source file  
    python_code = ice_to_python("source.ice")
    
    # Convert an entire CEdev project folder
    converted_files = convert_cedev_project("path/to/project", "output/folder")
    
    # Convert an entire ICE project folder
    converted_files = convert_ice_project("path/to/project", "output/folder")
"""

from __future__ import annotations

from .cedev_convert import cedev_to_python
from .ice_convert import ice_to_python
from .project_converter import convert_cedev_project, convert_ice_project, run

__all__ = ["cedev_to_python", "ice_to_python"]
