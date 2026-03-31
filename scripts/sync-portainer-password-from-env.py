#!/usr/bin/env python3
"""Пишет portainer_admin_password из .env (PORTAINER_ADMIN_PASSWORD) или changeme."""
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
env_path = root / ".env"
out_path = root / "portainer_admin_password"
default = "changeme"

val = default
if env_path.is_file():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("PORTAINER_ADMIN_PASSWORD="):
            val = s.split("=", 1)[1].strip().strip('"').strip("'")
            break

out_path.write_bytes(val.encode("utf-8"))
os.chmod(out_path, 0o600)
print(f"OK: {out_path} ({len(val)} bytes)", file=sys.stderr)
