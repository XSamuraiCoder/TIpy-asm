"""Persistent byte-file API backed by TI-84 Plus CE AppVars.

The Flash App backend gives each file an 8-character TI name and provides
existence, size, create/delete/clear, and byte access. Files are AppVars so
they survive application launches and can be managed with calculator tools.
"""

FILE_API = {
    "exists": (1, 1),
    "size": (1, 1),
    "create": (2, 2),
    "delete": (1, 1),
    "clear": (1, 1),
    "read_byte": (2, 2),
    "write_byte": (3, 3),
    "read_u16": (2, 2),
    "write_u16": (3, 3),
}
