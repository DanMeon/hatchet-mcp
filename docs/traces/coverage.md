# Spec ↔ Test Trace

Auto-generated — `scripts/generate_spec_trace.py`. Living.

Maps spec acceptance criteria (AC-N) ↔ tests, collected from `@pytest.mark.spec("vX.Y.Z/topic#AC-N")` markers (CONVENTIONS § Trace Report).

| Spec | AC | Tests |
|---|---|---|
| v0.2.0/reliability | — | `tests/test_reliability.py::test_404_surfaces_on_first_attempt` |
| v0.2.0/reliability | — | `tests/test_reliability.py::test_429_malformed_retry_after_ignored` |
| v0.2.0/reliability | — | `tests/test_reliability.py::test_429_retry_after_above_cap_clamps_to_10s` |
| v0.2.0/reliability | — | `tests/test_reliability.py::test_429_retry_after_below_backoff_keeps_backoff_floor` |
| v0.2.0/reliability | — | `tests/test_reliability.py::test_429_uses_backoff_when_no_retry_after` |
| v0.2.0/reliability | — | `tests/test_reliability.py::test_503_recovers_on_third_attempt` |
| v0.2.0/reliability | — | `tests/test_reliability.py::test_503_retries_three_times_then_surfaces` |
| v0.2.0/reliability | — | `tests/test_reliability.py::test_connection_error_retries` |
| v0.2.0/reliability | — | `tests/test_reliability.py::test_deadline_applies_to_non_idempotent_tools_too` |
| v0.2.0/reliability | — | `tests/test_reliability.py::test_deadline_surfaces_timeout` |
| v0.2.0/reliability | — | `tests/test_reliability.py::test_idempotent_mutation_503_retries` |
| v0.2.0/reliability | — | `tests/test_reliability.py::test_mutating_idempotency_split_matches_catalog` |
| v0.2.0/reliability | — | `tests/test_reliability.py::test_non_idempotent_503_surfaces_without_retry` |
| v0.2.0/reliability | AC-1 | `tests/test_reliability.py::test_404_surfaces_on_first_attempt` |
| v0.2.0/reliability | AC-1 | `tests/test_reliability.py::test_503_recovers_on_third_attempt` |
| v0.2.0/reliability | AC-1 | `tests/test_reliability.py::test_503_retries_three_times_then_surfaces` |
| v0.2.0/reliability | AC-1 | `tests/test_reliability.py::test_connection_error_retries` |
| v0.2.0/reliability | AC-2 | `tests/test_reliability.py::test_429_malformed_retry_after_ignored` |
| v0.2.0/reliability | AC-2 | `tests/test_reliability.py::test_429_retry_after_above_cap_clamps_to_10s` |
| v0.2.0/reliability | AC-2 | `tests/test_reliability.py::test_429_retry_after_below_backoff_keeps_backoff_floor` |
| v0.2.0/reliability | AC-2 | `tests/test_reliability.py::test_429_uses_backoff_when_no_retry_after` |
| v0.2.0/reliability | AC-3 | `tests/test_reliability.py::test_idempotent_mutation_503_retries` |
| v0.2.0/reliability | AC-3 | `tests/test_reliability.py::test_mutating_idempotency_split_matches_catalog` |
| v0.2.0/reliability | AC-3 | `tests/test_reliability.py::test_non_idempotent_503_surfaces_without_retry` |
| v0.2.0/reliability | AC-4 | `tests/test_reliability.py::test_deadline_applies_to_non_idempotent_tools_too` |
| v0.2.0/reliability | AC-4 | `tests/test_reliability.py::test_deadline_surfaces_timeout` |
