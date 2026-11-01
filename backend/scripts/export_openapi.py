"""Write the public API's OpenAPI document (operator-only routers are not registered unless CCRIG_ENABLE_STUDIO is set, so they are not included).

    python -m scripts.export_openapi ../frontend/src/api/openapi.json

The frontend turns it into TypeScript types with `npm run gen:api`.
"""
import json
import sys
from pathlib import Path

from app.main import app


def main(out: str) -> None:
    Path(out).write_text(json.dumps(app.openapi(), indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "openapi.json")
