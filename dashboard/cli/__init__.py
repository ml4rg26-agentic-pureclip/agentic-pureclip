"""Standalone CLI for building the dataset optimisation HTML report.

Reuses the pure renderer in ``dashboard.api.report`` (``render_report``) so the
report looks identical to the one the API serves, but reads a plain ``data.json``
instead of the live ``results/`` tree.
"""
