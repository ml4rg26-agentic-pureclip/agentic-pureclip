"""Enable ``python -m dashboard.cli data.json``."""

from .report_cli import app

if __name__ == "__main__":
    app()
