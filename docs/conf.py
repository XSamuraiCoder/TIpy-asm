"""Sphinx configuration. Build with: python -m sphinx -W -b html docs docs/_build/html"""

import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parent
sys.path.insert(0, str(DOCS.parent / "package"))    # a copy of main; the reference is read from it
sys.path.insert(0, str(DOCS / "_ext"))

project = "TIpy-asm"
author = "Akhilesh Gollapudi"
copyright = "the TIpy-asm authors"
release = "1.1.2"

extensions = ["myst_parser", "sphinx_rtd_theme", "tipy_api"]
exclude_patterns = ["_build"]
source_suffix = {".rst": "restructuredtext", ".md": "markdown"}

html_theme = "sphinx_rtd_theme"
html_theme_options = {"navigation_depth": 3, "collapse_navigation": False}
html_title = "TIpy-asm documentation"

# Library methods are shown as graphics.pixel(), not ti84.graphics.pixel().
add_module_names = False
python_display_short_literal_types = True
