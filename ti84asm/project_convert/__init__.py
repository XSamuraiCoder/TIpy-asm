"""Project conversion tools for importing CEdev and ICE projects.

This package provides tools to convert existing CEdev C projects and ICE
projects into TIpy-asm Python format.

Usage:
    from ti84asm.project_convert import cedev_to_python, ice_to_python
    
    # Convert a CEdev C source file
    python_code = cedev_to_python("source.c")
    
    # Convert an ICE source file  
    python_code = ice_to_python("source.ice")
"""

from __future__ import annotations

from .cedev_convert import cedev_to_python
from .ice_convert import ice_to_python

__all__ = ["cedev_to_python", "ice_to_python"]
