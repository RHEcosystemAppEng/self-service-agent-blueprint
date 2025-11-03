"""Service layer for managing session token counts in the database."""

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import RequestSession

logger = structlog.get_logger()


class SessionTokenService:
    """Service for managing token count persistence in sessions."""

    @staticmethod
    async def update_token_counts(
        db: AsyncSession,
        session_id: str,
        input_tokens: int,
        output_tokens: int,
    ) -> bool:
        """
        Update token counts for a session by adding the new token usage.

        Args:
            db: Database session
            session_id: The session ID to update
            input_tokens: Number of input tokens to add
            output_tokens: Number of output tokens to add

        Returns:
            True if successful, False otherwise
        """
        try:
            total_tokens = input_tokens + output_tokens

            # Update using SQL to atomically increment counters and track max values
            stmt = (
                update(RequestSession)
                .where(RequestSession.session_id == session_id)
                .values(
                    total_input_tokens=RequestSession.total_input_tokens + input_tokens,
                    total_output_tokens=RequestSession.total_output_tokens
                    + output_tokens,
                    total_tokens=RequestSession.total_tokens + total_tokens,
                    llm_call_count=RequestSession.llm_call_count + 1,
                    max_input_tokens_per_call=func.greatest(
                        RequestSession.max_input_tokens_per_call, input_tokens
                    ),
                    max_output_tokens_per_call=func.greatest(
                        RequestSession.max_output_tokens_per_call, output_tokens
                    ),
                    max_total_tokens_per_call=func.greatest(
                        RequestSession.max_total_tokens_per_call, total_tokens
                    ),
                )
            )

            result = await db.execute(stmt)
            await db.commit()

            if result.rowcount > 0:
                logger.debug(
                    "Token counts updated for session",
                    session_id=session_id,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                )
                return True
            else:
                logger.warning(
                    "Session not found when updating token counts",
                    session_id=session_id,
                )
                return False

        except Exception as e:
            logger.error(
                "Failed to update token counts",
                session_id=session_id,
                error=str(e),
            )
            await db.rollback()
            return False

    @staticmethod
    async def get_token_counts(
        db: AsyncSession, session_id: str
    ) -> dict[str, int] | None:
        """
        Get current token counts for a session.

        Args:
            db: Database session
            session_id: The session ID to query

        Returns:
            Dictionary with token counts or None if session not found
        """
        try:
            stmt = select(
                RequestSession.total_input_tokens,
                RequestSession.total_output_tokens,
                RequestSession.total_tokens,
                RequestSession.llm_call_count,
                RequestSession.max_input_tokens_per_call,
                RequestSession.max_output_tokens_per_call,
                RequestSession.max_total_tokens_per_call,
            ).where(RequestSession.session_id == session_id)

            result = await db.execute(stmt)
            row = result.first()

            if row:
                return {
                    "total_input_tokens": row[0] or 0,
                    "total_output_tokens": row[1] or 0,
                    "total_tokens": row[2] or 0,
                    "llm_call_count": row[3] or 0,
                    "max_input_tokens": row[4] or 0,
                    "max_output_tokens": row[5] or 0,
                    "max_total_tokens": row[6] or 0,
                }
            else:
                logger.warning(
                    "Session not found when getting token counts", session_id=session_id
                )
                return None

        except Exception as e:
            logger.error(
                "Failed to get token counts",
                session_id=session_id,
                error=str(e),
            )
            return None
