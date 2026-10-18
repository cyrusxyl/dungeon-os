"""Errors shared by the rules modules. This file imports nothing, so any module may import it."""


class RulesError(ValueError):
    """A rules command that cannot run. The message says how to fix it."""
