import asyncio
import os
from uuid import UUID

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

from app.db.models.indicator import Indicator
from app.db.models.ai_report import AnalysisReport
from app.services.indicator_service import get_asset_indicator_history
from sqlalchemy import select

ASSET_ID = UUID("e17dd491-8a98-47ec-afb6-e8cccae8c624")  # INTC
REPORT_ID = UUID("998e1c35-cb7a-4c73-abff-c83559b0c90f")  # owns the 2026-04-23 snapshots


async def main():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with AsyncSession(engine) as db:
        async with db.begin():
            report = await db.get(AnalysisReport, REPORT_ID)
            report.report_period_name = "Q1 2026"
            await db.flush()

            ind = (await db.execute(
                select(Indicator).where(Indicator.code == "per")
            )).scalar_one()
            history = await get_asset_indicator_history(db, ASSET_ID, ind)
            for h in history:
                print(f"per: date={h['as_of_date']} name={h['source_report_name']!r}")

            await db.rollback()
            print("Rolled back.")
    await engine.dispose()


asyncio.run(main())
