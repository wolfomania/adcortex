"""Write the API's JSON Schema, from which the frontend generates its types.

Usage: uv run python scripts/export_api_schema.py ../frontend/src/api/schema.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from neuromarketing.api.schemas import api_json_schema


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    target = Path(sys.argv[1])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(api_json_schema(), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
