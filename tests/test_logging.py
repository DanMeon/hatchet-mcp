"""muzzle_dependency_loggers() forces SDK/transport loggers to WARNING so DEBUG output cannot leak Authorization headers."""

import logging

from hatchet_mcp.server import _DEPENDENCY_LOGGERS, muzzle_dependency_loggers


def test_muzzle_silences_dependency_loggers():
    # Force a noisy DEBUG state first so the muzzle has something to override.
    for name in _DEPENDENCY_LOGGERS:
        logging.getLogger(name).setLevel(logging.DEBUG)

    muzzle_dependency_loggers()

    for name in _DEPENDENCY_LOGGERS:
        assert logging.getLogger(name).level == logging.WARNING, (
            f"{name} logger was not muzzled to WARNING"
        )


def test_muzzle_includes_expected_loggers():
    # The exact set is part of the contract: a downstream depending on this list
    # (e.g. a security review) should fail loudly if a transport library is dropped.
    assert "hatchet_sdk" in _DEPENDENCY_LOGGERS
    assert "aiohttp" in _DEPENDENCY_LOGGERS
    assert "httpx" in _DEPENDENCY_LOGGERS
    assert "grpc" in _DEPENDENCY_LOGGERS
