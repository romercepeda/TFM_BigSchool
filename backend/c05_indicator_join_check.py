import asyncio
import os
from uuid import UUID

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

from app.db.models.indicator import Indicator
from app.services.indicator_service import get_asset_indicator_history
from sqlalchemy import select

ASSET_ID = UUID("e17dd491-8a98-47ec-afb6-e8cccae8c624")  # INTC, has ai_analysis snapshots


async def main():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with AsyncSession(engine) as db:
        indicators = (await db.execute(
            select(Indicator).where(Indicator.update_strategy == "on_ai_analysis")
        )).scalars().all()
        for ind in indicators:
            history = await get_asset_indicator_history(db, ASSET_ID, ind)
            for h in history:
                print(f"{ind.code}: date={h['as_of_date']} source={h['source']} name={h['source_report_name']!r}")
    await engine.dispose()


asyncio.run(main())
