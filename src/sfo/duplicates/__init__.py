"""Read-only duplicate detection.

SFO can *find* likely duplicates; it never deletes, merges or overwrites
them. Every object produced here is pure data for display/reporting. The
only content equality SFO trusts is a full cryptographic hash of identical
sizes; same-name or same-metadata files with different hashes are reported
as NOT duplicates (they simply do not group).

Safety properties:
- read-only: uses only inspect / list_directory / hash_file
- symlinks are never followed (counted as skipped)
- special files (FIFOs, sockets, devices) are counted, never opened
- version-control internals (.git) and dependency trees are not treated
  as user files
- a file that changes while being hashed is excluded as STALE rather than
  allowed to produce a misleading result
"""
