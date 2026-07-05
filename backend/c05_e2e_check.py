"""One-off E2E smoke test for update_report_metadata against the real dev DB.

Runs inside a single transaction that is always rolled back at the end, so
the dev database is left untouched regardless of outcome.
"""
import asyncio
from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
import os

from app.db.models.ai_report import AnalysisReport
from app.db.models.indicator import IndicatorSnapshot
from app.services.ai_report_service import update_report_metadata, DateCollisionError
from sqlalchemy import select


REPORT_A = UUID("664718ac-9b62-4380-b341-4552f4b18188")  # currently 2026-03-28
REPORT_B = UUID("998e1c35-cb7a-4c73-abff-c83559b0c90f")  # currently 2026-04-23, same asset


async def main():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with AsyncSession(engine) as db:
        async with db.begin():
            report_a = await db.get(AnalysisReport, REPORT_A)
            print(f"BEFORE: report A date={report_a.report_date} source={report_a.report_date_source} name_source={report_a.report_period_name_source}")

            # 1) Happy path: move report A to an unoccupied date.
            updated = await update_report_metadata(
                db, report_a, new_report_date=date(2026, 5, 1), new_report_period_name="Q1 2026 (edited)"
            )
            await db.flush()
            print(f"AFTER MOVE: report A date={updated.report_date} source={updated.report_date_source} name={updated.report_period_name!r} name_source={updated.report_period_name_source}")

            snaps = (await db.execute(
                select(IndicatorSnapshot).where(IndicatorSnapshot.source_ref == str(REPORT_A))
            )).scalars().all()
            dates = {s.as_of_date for s in snaps}
            print(f"Report A's snapshot dates now: {dates} (expect exactly {{2026-05-01}})")

            # 2) Collision path: try moving report A onto report B's date (different analysis).
            try:
                await update_report_metadata(db, report_a, new_report_date=date(2026, 4, 23), new_report_period_name=None)
                await db.flush()
                print("COLLISION TEST FAILED: expected DateCollisionError, none raised")
            except DateCollisionError as exc:
                print(f"COLLISION TEST OK: got DateCollisionError({exc.conflicting_date})")

            # Verify nothing was partially written by the failed collision attempt.
            snaps_after = (await db.execute(
                select(IndicatorSnapshot).where(IndicatorSnapshot.source_ref == str(REPORT_A))
            )).scalars().all()
            dates_after = {s.as_of_date for s in snaps_after}
            print(f"Report A's snapshot dates after failed collision attempt: {dates_after} (expect unchanged {{2026-05-01}})")

            await db.rollback()
            print("Rolled back — dev DB left untouched.")

    await engine.dispose()


asyncio.run(main())
