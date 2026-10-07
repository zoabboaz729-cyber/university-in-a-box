"""Background scheduler for decoupled Roommate checks and web-push nudges."""
import asyncio

from app.ai.provider import get_provider
from app.db import get_connection
from app.monitor import get_logger
from app.roles import roommate
from app.roles.activity import current_streak
from app.scheduler.notifications import send_push_notification


class SchedulerService:
    """Minimal in-process scheduler that keeps the app responsive."""

    def __init__(self):
        self._task = None
        self._stop = asyncio.Event()

    async def start(self):
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        if self._task is None:
            return
        self._stop.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass

    async def _loop(self):
        while not self._stop.is_set():
            try:
                await self._run_tick()
            except Exception:
                get_logger().exception("Background scheduler tick failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=60)
            except TimeoutError:
                pass

    async def _run_tick(self):
        with get_connection() as conn:
            users = conn.execute(
                "SELECT id FROM users ORDER BY id"
            ).fetchall()

        for user in users:
            user_id = user["id"]
            try:
                created = await asyncio.to_thread(
                    roommate.generate_due_prompts,
                    get_provider(),
                    user_id,
                )
            except Exception:
                get_logger().warning(
                    "Background Roommate generation failed for user %s",
                    user_id,
                    exc_info=True,
                )
                continue

            if created:
                latest = roommate.latest_prompt(user_id)
                dedupe = f"roommate-prompt:{latest['id']}" if latest else None
                send_push_notification(
                    user_id,
                    "Roommate insight ready",
                    "A fresh cross-domain nudge is waiting for you.",
                    url="/roommate",
                    dedupe_key=dedupe,
                )

            streak = self._streak_nudge(user_id)
            if streak is not None:
                send_push_notification(
                    user_id,
                    "Study streak",
                    streak,
                    url="/",
                    dedupe_key=f"streak:{streak.split(':', 1)[0]}",
                )

    def _streak_nudge(self, user_id: int):
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT id FROM courses WHERE user_id = ? AND status = 'active'",
                (user_id,),
            ).fetchall()

        for row in rows:
            course_id = row["id"]
            streak = current_streak(course_id)
            if streak in (3, 7, 14, 30):
                return f"course:{course_id}:streak:{streak}"
        return None


scheduler = SchedulerService()


async def start_scheduler():
    await scheduler.start()


async def stop_scheduler():
    await scheduler.stop()
