"""Smart Folder Organizer (SFO).

A privacy-first Linux tool that organizes files locally.

Absolute safety contract (enforced architecturally, not by convention):

* never delete user files
* never modify file contents
* never overwrite existing files
* never execute files
* never upload anything
* organize only after an explicit, exact-word confirmation
"""

from __future__ import annotations

__version__ = "0.9.0"
