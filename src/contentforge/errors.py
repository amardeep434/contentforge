"""Exception hierarchy.

Every error this package raises descends from ContentforgeError, so callers can
distinguish our failures from library ones. Nothing here is ever caught-and-
defaulted internally: a stage that cannot get its input fails and writes nothing.
"""


class ContentforgeError(Exception):
    """Base for every error this package raises."""


class UnprovenancedError(ContentforgeError):
    """A value reached a stage boundary without a source."""


class QuotaExceededError(ContentforgeError):
    """The requested call would exceed the daily API budget."""


class MissingDataError(ContentforgeError):
    """Required input is absent. Never substitute a default."""
