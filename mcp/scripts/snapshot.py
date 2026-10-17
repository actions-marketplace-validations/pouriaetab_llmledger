"""Refresh the data snapshot bundled in the package (used only before the first download).
Run before each build: python scripts/snapshot.py [path or address of data.json]"""
import gzip
import json
import sys
import urllib.request
from pathlib import Path

SOURCE = sys.argv[1] if len(sys.argv) > 1 else "https://pouriaetab.github.io/llmledger/data.json"
DEST = Path(__file__).parent.parent / "src" / "llmledger_mcp" / "snapshot.json.gz"

if SOURCE.startswith("http"):
    with urllib.request.urlopen(urllib.request.Request(SOURCE, headers={"User-Agent": "llmledger-mcp"}), timeout=60) as r:
        body = r.read()
else:
    body = Path(SOURCE).read_bytes()
data = json.loads(body)
assert data.get("schema") == 1 and len(data["models"]) > 100, "not a llmledger data.json"
DEST.write_bytes(gzip.compress(json.dumps(data, separators=(",", ":")).encode(), 9, mtime=0))
print(f"{DEST.name}: {len(data['models']):,} models, built {data['built']}, {DEST.stat().st_size // 1024} KB")
