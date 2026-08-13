"""Error taxonomy: transport and state errors are exceptions; failure
conditions (FAILED / ANIMATED / EMPTY) are data carried in Output (ADR-0003)."""


class BrowserError(Exception):
    """Base for all errors crossing the core seam."""


class StateError(BrowserError):
    """Bad session state: malformed workflow JSON, unknown site, selection
    not in loaded results, etc."""


class TransportError(BrowserError):
    """Network or HTTP-level failure talking to a site API / file host."""
