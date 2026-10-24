"""Full project converter for CEdev and ICE projects.

This module provides tools to convert entire CEdev C projects or ICE projects
into TIpy-asm Python format, including:
- Main source files (.c or .ice)
- Header files (.h)
- Asset files (images, fonts, binary data)
- Makefile/builder configuration

Usage:
    from ti84asm.project_convert import convert_cedev_project, convert_ice_project
    
    # Convert a CEdev project folder
    convert_cedev_project("path/to/cedev_project", "output_folder")
    
    # Convert an ICE project file
    convert_ice_project("path/to/project.ice", "output_folder")
    
    # Or use the command-line tool:
    # tipy-asm convert-project --type cedev path/to/project -o output_folder
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from .cedev_convert import cedev_to_python
from .ice_convert import ice_to_python


# File extensions for different project types
CEDEV_C_EXTENSIONS = (".c", ".h")
ICE_EXTENSIONS = (".ice",)

# Known asset file types
ASSET_EXTENSIONS = (
    ".png", ".bmp", ".jpg", ".jpeg",  # Images
    ".ttf", ".otf", ".fnt",            # Fonts
    ".bin", ".csv",                     # Binary data
)


class ProjectConverter:
    """Converts an entire CEdev or ICE project to TIpy-asm Python."""
    
    def __init__(self, project_path: Path, output_path: Path, project_type: str = "cedev"):
        """
        Initialize the converter.
        
        Args:
            project_path: Path to the project folder or file
            output_path: Path to save converted files
            project_type: "cedev" or "ice"
        """
        self.project_path = Path(project_path)
        self.output_path = Path(output_path)
        self.project_type = project_type
        self.converted_files = []
        
        if not self.project_path.exists():
            raise FileNotFoundError(f"Project path not found: {project_path}")
        
        self.output_path.mkdir(parents=True, exist_ok=True)
    
    def convert(self) -> list[Path]:
        """Convert the entire project."""
        if self.project_type == "cedev":
            return self._convert_cedev_project()
        elif self.project_type == "ice":
            return self._convert_ice_project()
        else:
            raise ValueError(f"Unknown project type: {self.project_type}")
    
    def _convert_cedev_project(self) -> list[Path]:
        """Convert a CEdev C project."""
        # Find all C and H files
        source_files = []
        for ext in CEDEV_C_EXTENSIONS:
            source_files.extend(self.project_path.rglob(f"*{ext}"))
        
        # Also check for a makefile
        makefile = self.project_path / "makefile"
        if makefile.exists():
            # Parse makefile to get source files
            makefile_sources = self._parse_makefile(makefile)
            source_files = [self.project_path / src for src in makefile_sources if (self.project_path / src).exists()]
        
        # Convert each source file
        for src_file in source_files:
            if src_file.suffix.lower() == ".h":
                # Header files - convert to Python with type hints
                self._convert_header_file(src_file)
            else:
                # C source files - convert to Python
                self._convert_source_file(src_file)
        
        # Copy or convert assets
        self._convert_assets()
        
        # Create a main.py if we converted multiple files
        if len(source_files) > 1:
            self._create_main_python()
        
        # Create a pyproject.toml
        self._create_pyproject_toml()
        
        return self.converted_files
    
    def _convert_ice_project(self) -> list[Path]:
        """Convert an ICE project."""
        # ICE projects are typically single files
        if self.project_path.is_file():
            return self._convert_single_ice_file(self.project_path)
        else:
            # Find all ICE files
            ice_files = list(self.project_path.rglob("*" + ICE_EXTENSIONS[0]))
            for ice_file in ice_files:
                self._convert_single_ice_file(ice_file)
            return self.converted_files
    
    def _convert_single_ice_file(self, ice_file: Path) -> list[Path]:
        """Convert a single ICE file."""
        output_file = self.output_path / (ice_file.stem + ".py")
        content = ice_file.read_text(encoding="utf-8")
        python_code = ice_to_python(content)
        output_file.write_text(python_code, encoding="utf-8")
        self.converted_files.append(output_file)
        return [output_file]
    
    def _convert_source_file(self, c_file: Path) -> None:
        """Convert a C source file."""
        relative_path = c_file.relative_to(self.project_path)
        output_file = self.output_path / (relative_path.with_suffix(".py"))
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        content = c_file.read_text(encoding="utf-8")
        python_code = cedev_to_python(content)
        
        # Clean up the output
        python_code = self._clean_converted_code(python_code)
        
        output_file.write_text(python_code, encoding="utf-8")
        self.converted_files.append(output_file)
    
    def _convert_header_file(self, h_file: Path) -> None:
        """Convert a C header file to Python with type hints."""
        relative_path = h_file.relative_to(self.project_path)
        output_file = self.output_path / (relative_path.with_suffix(".pyi"))
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        content = h_file.read_text(encoding="utf-8")
        
        # Convert header file (simplified - just extract function declarations)
        python_code = self._convert_header_to_pyi(content)
        
        output_file.write_text(python_code, encoding="utf-8")
        self.converted_files.append(output_file)
    
    def _parse_makefile(self, makefile: Path) -> list[str]:
        """Parse a CEdev makefile to find source files."""
        sources = []
        with open(makefile, "r") as f:
            for line in f:
                line = line.strip()
                # Look for SRCS variable
                if line.startswith("SRCS") or "SRCS" in line:
                    # Extract file list
                    match = re.search(r"SRCS\s*[+=]\s*(.+)", line)
                    if match:
                        files = match.group(1).split()
                        for file_pattern in files:
                            # Handle wildcard patterns
                            if "wildcard" in file_pattern or "*" in file_pattern:
                                # Extract the pattern (e.g., "src/*.c" or "$(wildcard src/*.c)")
                                pattern = file_pattern.replace("$(wildcard ", "").replace(")", "")
                                # Find files matching the pattern
                                import glob
                                matched_files = glob.glob(str(self.project_path / pattern))
                                sources.extend([Path(f).relative_to(self.project_path).as_posix() for f in matched_files])
                            else:
                                sources.append(file_pattern)
                # Look for source files in wildcard patterns
                elif "*" in line and ".c" in line:
                    # Try to extract pattern
                    match = re.search(r'"?\$?\(?wildcard\s+([^)]+)\)?"?', line)
                    if not match:
                        match = re.search(r'"?([^*"]*\*[^""]*)"?', line)
                    if match:
                        pattern = match.group(1).replace("wildcard ", "")
                        import glob
                        matched_files = glob.glob(str(self.project_path / pattern))
                        sources.extend([Path(f).relative_to(self.project_path).as_posix() for f in matched_files])
        return sources
    
    def _convert_header_to_pyi(self, content: str) -> str:
        """Convert a C header file to Python type stub."""
        lines = []
        in_function_decl = False
        
        for line in content.split("\n"):
            line = line.strip()
            
            # Skip comments and preprocessor directives
            if line.startswith("//") or line.startswith("/*") or line.startswith("#"):
                continue
            if "*/" in line:
                continue
            
            # Function declarations
            if line.endswith(";") and "(" in line:
                # Convert: return_type func_name(params); -> def func_name(params) -> return_type: ...
                match = re.match(r"(\w+)\s+(\w+)\(([^)]*)\)\s*;", line)
                if match:
                    return_type, func_name, params = match.groups()
                    py_return = "None" if return_type == "void" else return_type.lower()
                    lines.append(f"def {func_name}({params}) -> {py_return}: ...")
            
            # Constants
            elif line.startswith("#define"):
                match = re.match(r"#define\s+(\w+)\s+(\w+)", line)
                if match:
                    const_name, const_value = match.groups()
                    lines.append(f"{const_name}: int = {const_value}")
            
            # Type definitions
            elif line.startswith("typedef"):
                match = re.match(r"typedef\s+\w+\s+(\w+)\s*;", line)
                if match:
                    type_name = match.group(1)
                    lines.append(f"class {type_name}: ...")
        
        return "\n".join(lines)
    
    def _convert_assets(self) -> None:
        """Convert asset files (images, fonts, binary data)."""
        for asset_file in self.project_path.rglob("*"):
            if asset_file.suffix.lower() in ASSET_EXTENSIONS:
                relative_path = asset_file.relative_to(self.project_path)
                output_path = self.output_path / "assets" / relative_path.name
                output_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Copy the asset file
                import shutil
                shutil.copy2(asset_file, output_path)
                self.converted_files.append(output_path)
    
    def _create_main_python(self) -> None:
        """Create a main.py file that imports and runs the converted code."""
        main_file = self.output_path / "main.py"
        
        # Find the main source file
        main_source = None
        for f in self.converted_files:
            if f.suffix == ".py" and "main" in f.name:
                main_source = f
                break
        
        if main_source:
            # Import and call the main function
            module_name = main_source.stem
            main_file.write_text(f"from {module_name} import main\n\nmain()\n", encoding="utf-8")
            self.converted_files.append(main_file)
        else:
            # Just create an empty main
            main_file.write_text("# Main entry point\n", encoding="utf-8")
            self.converted_files.append(main_file)
    
    def _create_pyproject_toml(self) -> None:
        """Create a pyproject.toml for the converted project."""
        toml_file = self.output_path / "pyproject.toml"
        
        # Find the project name
        project_name = self.project_path.name.replace("-", "_").replace(" ", "_")
        
        content = f"""[tool.tipy]
name = "{project_name}"
target = "ce"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
"""
        toml_file.write_text(content, encoding="utf-8")
        self.converted_files.append(toml_file)
    
    def _clean_converted_code(self, code: str) -> str:
        """Clean up converted code."""
        # Remove duplicate imports
        lines = code.split("\n")
        seen_imports = set()
        cleaned_lines = []
        
        for line in lines:
            if line.startswith("from ti84 import"):
                if line not in seen_imports:
                    seen_imports.add(line)
                    cleaned_lines.append(line)
            else:
                cleaned_lines.append(line)
        
        return "\n".join(cleaned_lines)


def convert_cedev_project(project_path: str | Path, output_path: str | Path) -> list[Path]:
    """Convert a CEdev project to TIpy-asm Python.
    
    Args:
        project_path: Path to the CEdev project folder
        output_path: Path to save the converted project
        
    Returns:
        List of converted files
    """
    converter = ProjectConverter(project_path, output_path, "cedev")
    return converter.convert()


def convert_ice_project(project_path: str | Path, output_path: str | Path) -> list[Path]:
    """Convert an ICE project to TIpy-asm Python.
    
    Args:
        project_path: Path to the ICE project folder or file
        output_path: Path to save the converted project
        
    Returns:
        List of converted files
    """
    converter = ProjectConverter(project_path, output_path, "ice")
    return converter.convert()


def add_arguments(parser):
    """Add command-line arguments for convert-project."""
    parser.add_argument("project", type=Path, help="Path to CEdev/ICE project folder or file")
    parser.add_argument("-o", "--output", type=Path, help="Output folder (default: project_converted)")
    parser.add_argument("--type", choices=["cedev", "ice"], default="cedev",
                        help="Project type: cedev or ice (default: cedev)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed conversion info")


def run(args):
    """Run the project conversion."""
    import sys
    
    output_path = args.output or (args.project.parent / f"{args.project.name}_converted")
    
    if args.verbose:
        print(f"Converting {args.project} to {output_path}")
        print(f"Project type: {args.type}")
    
    try:
        if args.type == "cedev":
            files = convert_cedev_project(args.project, output_path)
        else:
            files = convert_ice_project(args.project, output_path)
        
        if args.verbose:
            print(f"Converted {len(files)} files:")
            for f in files:
                print(f"  - {f.relative_to(output_path)}")
        
        return files
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        raise
