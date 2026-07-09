"""Run scheduling: turn a UI/CLI run request into an overnight-batch manifest.

``schedule.build_manifest`` is the single source of truth shared by the dashboard
API (``dashboard.api.collectors``) and the ``agentic-pureclip-run`` CLI, so a run
started from the Plan page and one started from the terminal are byte-identical.
"""
