"""Process-wide Hatchet client.

Constructing ``Hatchet()`` performs no network I/O: gRPC channels are created lazily and
the read tools only ever touch the REST API. Construction does, however, validate the
token via the SDK's ``ClientConfig``, which is part of our fail-fast startup path.
"""

import threading

from hatchet_sdk import Hatchet
from hatchet_sdk.clients.rest.api_client import ApiClient
from hatchet_sdk.clients.v1.api_client import BaseRestClient

from hatchet_mcp.config import ConfigError

_hatchet: Hatchet | None = None
_rest: BaseRestClient | None = None
_api_client: ApiClient | None = None
# Guards the double-checked init of _api_client: _rest_call runs in asyncio.to_thread,
# so multiple workers can race past `if _api_client is None` and build two PoolManagers.
_api_client_lock = threading.Lock()


def init_hatchet() -> Hatchet:
    """Construct and cache the Hatchet client, failing fast on an invalid token.

    The SDK's own validation error embeds a prefix of the token, so we never propagate its
    message — only the exception type name, which leaks nothing.
    """
    global _hatchet
    if _hatchet is None:
        try:
            _hatchet = Hatchet()
        except Exception as exc:  # noqa: BLE001 - re-raised cleanly, without the token
            raise ConfigError(
                f"Failed to initialise the Hatchet client ({type(exc).__name__}). "
                "Verify HATCHET_CLIENT_TOKEN is a valid Hatchet JWT "
                "(and HATCHET_CLIENT_SERVER_URL if you override it)."
            ) from None
    return _hatchet


def get_hatchet() -> Hatchet:
    """Return the cached Hatchet client, constructing it on first use."""
    if _hatchet is None:
        return init_hatchet()
    return _hatchet


def get_rest() -> BaseRestClient:
    """Return a cached low-level REST client for endpoints without an ``aio_*`` method.

    A few reads (v1 events, OTel traces, run timings) have no feature-client
    wrapper, so they go through the generated REST API classes. This shares the cached
    Hatchet client's ``ClientConfig`` — same token, same tenant, same server URL.
    """
    global _rest
    if _rest is None:
        _rest = BaseRestClient(get_hatchet().config)
    return _rest


def get_api_client() -> ApiClient:
    """Return a process-wide ``ApiClient`` that reuses one ``urllib3.PoolManager``.

    Each ``ApiClient()`` build constructs a new ``RESTClientObject`` and ``urllib3.PoolManager``,
    so calling ``BaseRestClient.client()`` per request throws away every connection. Caching
    one instance lets keep-alive amortize TCP/TLS across calls. ``ApiClient.__exit__`` is a
    no-op (rest/api_client.py:93-97), so skipping the ``with`` block leaks nothing; the
    underlying PoolManager is thread-safe. The double-checked lock guards against the
    ``asyncio.to_thread`` workers in ``_rest_call`` racing past the ``None`` check.
    """
    global _api_client
    if _api_client is None:
        with _api_client_lock:
            if _api_client is None:
                _api_client = ApiClient(get_rest().api_config)
    return _api_client
