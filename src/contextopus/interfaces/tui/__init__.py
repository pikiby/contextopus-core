"""Inline terminal interface; importing this module needs no UI dependencies."""


def run(application):
    from .app import ContextopusApp

    ContextopusApp(application).run(inline=True, mouse=False)
