"""Unit tests for session request serialization.

Covers: session lock key derivation, reconstruct_normalized_request,
acquire/release session lock with mocked DB, SessionLockTimeoutError → 503,
dequeue_oldest_pending, reclaim_stuck_processing, wait_for_turn_and_process_one.
"""

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from request_manager.exceptions import SessionLockTimeoutError
from request_manager.main import app
from request_manager.session_config import (
    AGENT_TIMEOUT,
    SESSION_LOCK_STUCK_BUFFER_SECONDS,
)
from request_manager.session_lock import acquire_session_lock, release_session_lock
from request_manager.session_orchestrator import (
    _get_stuck_cutoff,
    dequeue_oldest_pending,
    reclaim_stuck_processing,
    reconstruct_normalized_request,
    wait_for_turn_and_process_one,
)
from shared_models.models import IntegrationType, NormalizedRequest, RequestStatus
from shared_models.session_lock import session_id_to_lock_key


class TestSessionLockKeyDerivation:
    """Test session_id to advisory lock key mapping."""

    def test_same_session_id_produces_same_key(self) -> None:
        """Same session_id must always map to the same bigint key."""
        session_id = "550e8400-e29b-41d4-a716-446655440000"
        key1 = session_id_to_lock_key(session_id)
        key2 = session_id_to_lock_key(session_id)
        assert key1 == key2

    def test_different_session_ids_produce_different_keys(self) -> None:
        """Different session_ids should map to different keys (collision avoidance).

        Use UUIDs that differ in the first 16 hex chars (used for key derivation).
        """
        key1 = session_id_to_lock_key("550e8400-e29b-41d4-a716-446655440000")
        key2 = session_id_to_lock_key("660e8400-e29b-41d4-a716-446655440000")
        assert key1 != key2

    def test_key_is_non_negative(self) -> None:
        """Key must be non-negative (PostgreSQL advisory lock constraint)."""
        for sid in [
            "550e8400-e29b-41d4-a716-446655440000",
            "ffffffff-ffff-ffff-ffff-ffffffffffff",
        ]:
            key = session_id_to_lock_key(sid)
            assert key >= 0
            assert key <= 0x7FFF_FFFF_FFFF_FFFF

    def test_uuid_format(self) -> None:
        """Key from standard UUID matches plan formula."""
        session_id = "550e8400-e29b-41d4-a716-446655440000"
        key = session_id_to_lock_key(session_id)
        expected = int(uuid.UUID(session_id).hex[:16], 16) & 0x7FFF_FFFF_FFFF_FFFF
        assert key == expected

    def test_non_uuid_fallback(self) -> None:
        """Non-UUID session_ids use deterministic SHA-256 fallback."""
        key = session_id_to_lock_key("non-uuid-session-123")
        assert isinstance(key, int)
        assert key >= 0
        assert key <= 0x7FFF_FFFF_FFFF_FFFF

    def test_non_uuid_deterministic(self) -> None:
        """Same non-UUID session_id always produces same key (required for multi-pod locking)."""
        sid = "non-uuid-session-456"
        key1 = session_id_to_lock_key(sid)
        key2 = session_id_to_lock_key(sid)
        assert key1 == key2


class TestReconstructNormalizedRequest:
    """Test NormalizedRequest reconstruction from RequestLog."""

    def test_reconstruct_with_full_normalized_request(self) -> None:
        """Reconstruct when normalized_request has all fields."""
        created = datetime.now(timezone.utc)

        # Create a minimal RequestLog-like object (we use a simple mock)
        class MockRequestLog:
            request_id = "req-123"
            session_id = "sess-456"
            request_content = "Hello"
            normalized_request = {
                "user_id": "user-789",
                "integration_type": "SLACK",
                "content": "Hello",
                "request_type": "message",
                "integration_context": {"channel_id": "C123"},
                "user_context": {"name": "Alice"},
                "target_agent_id": "agent-1",
                "requires_routing": False,
            }
            created_at = created

        nr = reconstruct_normalized_request(MockRequestLog())
        assert nr.request_id == "req-123"
        assert nr.session_id == "sess-456"
        assert nr.user_id == "user-789"
        assert nr.integration_type == IntegrationType.SLACK
        assert nr.content == "Hello"
        assert nr.request_type == "message"
        assert nr.integration_context == {"channel_id": "C123"}
        assert nr.user_context == {"name": "Alice"}
        assert nr.target_agent_id == "agent-1"
        assert nr.requires_routing is False
        assert nr.created_at == created

    def test_reconstruct_with_minimal_normalized_request(self) -> None:
        """Reconstruct with defaults when normalized_request is sparse."""
        created = datetime.now(timezone.utc)

        class MockRequestLog:
            request_id = "req-1"
            session_id = "sess-1"
            request_content = "Hi"
            normalized_request = {"user_id": "u1", "integration_type": "WEB"}
            created_at = created

        nr = reconstruct_normalized_request(MockRequestLog())
        assert nr.request_id == "req-1"
        assert nr.session_id == "sess-1"
        assert nr.user_id == "u1"
        assert nr.integration_type == IntegrationType.WEB
        assert nr.request_type == "unknown"
        assert nr.content == "Hi"
        assert nr.integration_context == {}
        assert nr.user_context == {}
        assert nr.target_agent_id is None
        assert nr.requires_routing is True

    def test_reconstruct_with_empty_or_none_normalized_request(self) -> None:
        """Reconstruct when normalized_request is None or empty (uses fallbacks)."""
        created = datetime.now(timezone.utc)

        class MockRequestLog:
            request_id = "req-2"
            session_id = "sess-2"
            request_content = "Fallback"
            normalized_request = None
            created_at = created

        nr = reconstruct_normalized_request(MockRequestLog())
        assert nr.request_id == "req-2"
        assert nr.session_id == "sess-2"
        assert nr.user_id == "unknown"
        assert nr.integration_type == IntegrationType.WEB
        assert nr.content == "Fallback"


@pytest.mark.asyncio
class TestSessionLockAcquireRelease:
    """Test session lock acquire/release with mocked DB."""

    async def test_acquire_returns_true_when_lock_granted(self) -> None:
        """Acquire returns True when pg_try_advisory_lock succeeds."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (True,)
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await acquire_session_lock(
            "550e8400-e29b-41d4-a716-446655440000", mock_db, timeout_seconds=1.0
        )
        assert result is True
        # pg_try_advisory_lock only
        assert mock_db.execute.call_count >= 1

    async def test_acquire_returns_false_on_timeout(self) -> None:
        """Acquire returns False when pg_try_advisory_lock never grants (timeout)."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (False,)  # Lock never acquired
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await acquire_session_lock(
            "550e8400-e29b-41d4-a716-446655440000",
            mock_db,
            timeout_seconds=0.05,  # Short timeout for test
        )
        assert result is False

    async def test_release_does_not_raise(self) -> None:
        """Release session lock completes without error."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (True, 12345)  # released, backend_pid
        mock_db.execute = AsyncMock(return_value=mock_result)

        await release_session_lock("550e8400-e29b-41d4-a716-446655440000", mock_db)
        mock_db.execute.assert_called_once()


class TestSessionLockTimeoutReturns503:
    """Test that SessionLockTimeoutError results in HTTP 503."""

    def test_session_lock_timeout_returns_503(self) -> None:
        """When session lock times out, generic endpoint returns 503 Service Unavailable."""
        from shared_models import get_db_session_dependency
        from sqlalchemy.ext.asyncio import AsyncSession

        client = TestClient(app)
        mock_session = MagicMock(spec=AsyncSession)

        async def override_get_db() -> AsyncSession:
            return mock_session

        # Patch unified_processor to have process_request_sync raise SessionLockTimeoutError
        mock_processor = MagicMock()
        mock_processor.process_request_sync = AsyncMock(
            side_effect=SessionLockTimeoutError(
                "Session lock timeout - too many concurrent requests for this session"
            )
        )

        app.dependency_overrides[get_db_session_dependency] = override_get_db

        with patch("request_manager.main.unified_processor", mock_processor):
            response = client.post(
                "/api/v1/requests/generic",
                json={
                    "user_id": "test-user",
                    "content": "Hello",
                    "integration_type": "CLI",
                    "request_type": "message",
                },
                headers={"x-user-id": "test-user"},
            )

        app.dependency_overrides.pop(get_db_session_dependency, None)

        assert response.status_code == 503
        body = response.json()
        assert "Service temporarily unavailable" in (
            body.get("detail", "") or body.get("error", "")
        )


class TestStuckCutoff:
    """Test _get_stuck_cutoff for reclaim time-based logic."""

    def test_stuck_cutoff_is_in_past(self) -> None:
        """Stuck cutoff should be AGENT_TIMEOUT + buffer seconds ago."""
        cutoff = _get_stuck_cutoff()
        now = datetime.now(timezone.utc)
        expected_seconds = AGENT_TIMEOUT + SESSION_LOCK_STUCK_BUFFER_SECONDS
        delta = (now - cutoff).total_seconds()
        assert abs(delta - expected_seconds) < 2  # Allow 2s variance


@pytest.mark.asyncio
class TestDequeueOldestPending:
    """Test dequeue_oldest_pending with mocked DB."""

    async def test_dequeue_returns_none_when_no_pending(self) -> None:
        """Dequeue returns None when no pending rows for session."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        result = await dequeue_oldest_pending("sess-123", mock_db, "pod-1")
        assert result is None

    async def test_dequeue_returns_row_and_sets_status_pod_name(self) -> None:
        """Dequeue returns oldest pending row with status=processing, pod_name set."""
        mock_row = MagicMock()
        mock_row.request_id = "req-1"
        mock_row.session_id = "sess-123"
        mock_row.request_content = "Hello"
        mock_row.normalized_request = {"user_id": "u1", "integration_type": "WEB"}
        mock_row.created_at = datetime.now(timezone.utc)

        mock_updated_row = MagicMock()
        mock_updated_row.request_id = "req-1"
        mock_updated_row.session_id = "sess-123"
        mock_updated_row.status = RequestStatus.PROCESSING.value
        mock_updated_row.pod_name = "pod-1"
        mock_updated_row.processing_started_at = datetime.now(timezone.utc)
        mock_updated_row.request_content = "Hello"
        mock_updated_row.normalized_request = {
            "user_id": "u1",
            "integration_type": "WEB",
        }
        mock_updated_row.created_at = mock_row.created_at

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        execute_results = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_row)),
            MagicMock(),
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_updated_row)),
        ]
        mock_db.execute = AsyncMock(side_effect=execute_results)

        result = await dequeue_oldest_pending("sess-123", mock_db, "pod-1")
        assert result is not None
        assert result.request_id == "req-1"
        assert result.status == RequestStatus.PROCESSING.value
        assert result.pod_name == "pod-1"
        assert result.processing_started_at is not None
        mock_db.commit.assert_called_once()


@pytest.mark.asyncio
class TestReclaimStuckProcessing:
    """Test reclaim_stuck_processing with mocked DB."""

    async def test_reclaim_returns_zero_when_no_stuck(self) -> None:
        """Reclaim returns 0 when no stuck processing rows (UPDATE affects 0 rows)."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        count = await reclaim_stuck_processing("sess-123", mock_db)
        assert count == 0

    async def test_reclaim_returns_count_when_stuck_rows_exist(self) -> None:
        """Reclaim returns count and commits when stuck processing rows exist (time-based or heartbeat)."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [("req-stuck-1",)]
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        count = await reclaim_stuck_processing("sess-123", mock_db)
        assert count == 1
        mock_db.commit.assert_called_once()


class TestDuplicateCloudEventReturnsSkipped:
    """Test that duplicate CloudEvent delivery returns skip response."""

    def test_duplicate_request_created_returns_skipped(self) -> None:
        """Send same REQUEST_CREATED event twice; second returns status=skipped."""
        from request_manager.main import app
        from shared_models import EventTypes, get_db_session_dependency
        from sqlalchemy.ext.asyncio import AsyncSession

        event_id = "evt-dup-test-123"
        payload = {
            "specversion": "1.0",
            "type": EventTypes.REQUEST_CREATED,
            "source": "integration-dispatcher",
            "id": event_id,
            "data": {
                "request_id": "req-1",
                "session_id": "sess-1",
                "user_id": "u1",
                "content": "Hello",
                "integration_type": "SLACK",
                "request_type": "message",
                "metadata": {},
            },
        }
        call_count = 0

        async def mock_try_claim(*args: object, **kwargs: object) -> bool:
            nonlocal call_count
            call_count += 1
            return call_count == 1

        mock_db = MagicMock(spec=AsyncSession)

        async def override_get_db() -> AsyncSession:
            return mock_db

        app.dependency_overrides[get_db_session_dependency] = override_get_db

        try:
            with (
                patch(
                    "request_manager.database_utils.try_claim_event_for_processing",
                    new_callable=AsyncMock,
                    side_effect=mock_try_claim,
                ),
                patch(
                    "request_manager.main._handle_request_created_event_from_data",
                    new_callable=AsyncMock,
                    return_value={"status": "ok"},
                ),
            ):
                client = TestClient(app)
                response1 = client.post(
                    "/api/v1/events/cloudevents",
                    json=payload,
                    headers={"Content-Type": "application/cloudevents+json"},
                )
                assert response1.status_code == 200
                body1 = response1.json()
                assert body1.get("status") != "skipped"

                response2 = client.post(
                    "/api/v1/events/cloudevents",
                    json=payload,
                    headers={"Content-Type": "application/cloudevents+json"},
                )
                assert response2.status_code == 200
                body2 = response2.json()
                assert body2.get("status") == "skipped"
                assert "duplicate" in body2.get("reason", "").lower()
                assert body2.get("event_id") == event_id
        finally:
            app.dependency_overrides.pop(get_db_session_dependency, None)


@pytest.mark.asyncio
class TestWaitForTurnAndProcessOne:
    """Test wait_for_turn_and_process_one error paths."""

    async def test_raises_when_strategy_send_fails_for_our_request(self) -> None:
        """When strategy_send_request returns False for our request, raises Exception."""
        session_id = "sess-123"
        our_request_id = "req-ours"
        mock_db = AsyncMock()
        mock_lock_db = AsyncMock()

        # Phase 1: check returns None (no existing row), so create_request_log_entry_unified is called
        check_result = MagicMock()
        check_result.scalar_one_or_none.return_value = None
        mock_lock_db.execute = AsyncMock(return_value=check_result)
        mock_lock_db.commit = AsyncMock()

        mock_request_log = MagicMock()
        mock_request_log.request_id = our_request_id
        mock_request_log.session_id = session_id
        mock_request_log.normalized_request = {
            "user_id": "u1",
            "integration_type": "WEB",
        }
        mock_request_log.request_content = "Hi"
        mock_request_log.created_at = datetime.now(timezone.utc)

        normalized = NormalizedRequest(
            request_id=our_request_id,
            session_id=session_id,
            user_id="u1",
            integration_type=IntegrationType.WEB,
            request_type="message",
            content="Hi",
            integration_context={},
            user_context={},
            target_agent_id=None,
            requires_routing=True,
            created_at=datetime.now(timezone.utc),
        )

        async def fake_send(nr: NormalizedRequest) -> bool:
            return False

        async def fake_wait(req_id: str, timeout: int, db: Any) -> dict[str, Any]:
            return {"request_id": req_id, "content": "ok"}

        mock_get_session = AsyncMock()
        mock_get_session.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_get_session.__aexit__ = AsyncMock(return_value=None)
        mock_db_manager = MagicMock()
        mock_db_manager.get_session.return_value = mock_get_session

        async def mock_with_session_lock(
            _sid: str, _mgr: Any, fn: Any, **kw: Any
        ) -> Any:
            return await fn(mock_lock_db)

        with (
            patch(
                "request_manager.session_orchestrator.with_session_lock",
                new_callable=AsyncMock,
                side_effect=mock_with_session_lock,
            ),
            patch(
                "request_manager.session_orchestrator.get_database_manager",
                return_value=mock_db_manager,
            ),
            patch(
                "request_manager.database_utils.create_request_log_entry_unified",
                new_callable=AsyncMock,
            ),
            patch(
                "request_manager.session_orchestrator.get_pod_name",
                return_value="pod-1",
            ),
            patch(
                "request_manager.session_orchestrator.reclaim_stuck_processing",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "request_manager.session_orchestrator.dequeue_oldest_pending",
                new_callable=AsyncMock,
                return_value=mock_request_log,
            ),
        ):
            with pytest.raises(Exception, match="Failed to send request to agent"):
                await wait_for_turn_and_process_one(
                    session_id=session_id,
                    our_request_id=our_request_id,
                    normalized_request=normalized,
                    db=mock_db,
                    strategy_send_request=fake_send,
                    strategy_wait_for_response=fake_wait,
                    timeout=60,
                )
