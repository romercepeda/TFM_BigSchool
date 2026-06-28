"""
Script de simulación: inyecta en la BD el resultado de un análisis IA
como si el worker Celery lo hubiera procesado correctamente.

Uso (desde dentro del contenedor):
    docker compose exec backend python inject_ai_report.py

Datos hardcodeados:
    - Holding: Intel (INTC) de romer@romer.com / Cartera Personal
    - Resultado: el JSON devuelto por la IA externa
"""

import asyncio
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# ── Configuración ─────────────────────────────────────────────────────────────

HOLDING_ID = UUID("871e9a16-062b-40fc-9cfb-577a21483438")   # INTC / Cartera Personal
USER_ID    = UUID("7bf72066-8cd2-4bba-81c0-dbaf82c12655")   # romer@romer.com

# Resultado devuelto por la IA externa
AI_RESULT = {
    "report_date": "2026-03-28",
    "metrics": {
        "per": None,
        "roe": -0.132,
        "debt_ebitda": None,
        "revenue_growth_yoy": 0.0718,
        "analyst_sentiment": "mixed",
    },
    "executive_summary": (
        "• Q1 2026 revenue increased 7.2% year-over-year to $13.6 billion, driven by higher "
        "server pricing despite volume constraints from supply chain limitations\n"
        "• Company recognized $3.9 billion non-cash goodwill impairment primarily affecting "
        "Mobileye reporting unit due to increased macroeconomic and competitive uncertainty\n"
        "• Restructuring charges surged to $4.1 billion in Q1 2026 versus $156 million prior "
        "year, reflecting ongoing organizational realignment under 2025 Restructuring Plan\n"
        "• Intel Products segments demonstrated margin improvement with gross profit up 14% and "
        "operating margins expanding, partially offset by Intel Foundry losses\n"
        "• Significant geopolitical and supply chain risks identified, including Middle East "
        "conflict threatening Israeli manufacturing facility and critical component shortages"
    ),
    "global_signal": "bearish",
    "confidence_notes": (
        "P/E ratio not calculable due to net losses of $3.7 billion. Debt/EBITDA not meaningful "
        "with near-zero EBITDA. ROE annualized from quarterly loss of $3,728M against average "
        "stockholders' equity of $112.8B. Company facing substantial near-term headwinds: $3.9B "
        "asset impairment, $4.1B restructuring costs, supply constraints, manufacturing risks "
        "from geopolitical conflict, and competitive pressures."
    ),
}

PROVIDER      = "gemini"
MODEL_VERSION = "models/gemini-3-flash-preview (simulated)"

# ── Engine ────────────────────────────────────────────────────────────────────

import os
engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _find_asset_id(db: AsyncSession) -> UUID:
    from app.db.models.holding import Holding
    h = await db.get(Holding, HOLDING_ID)
    if h is None:
        raise RuntimeError(f"Holding {HOLDING_ID} not found")
    return h.asset_id


async def _upsert_indicator_snapshots(
    db: AsyncSession,
    asset_id: UUID,
    metrics: dict,
    report_id: UUID,
    as_of_date: date,
) -> int:
    from app.db.models.indicator import Indicator, IndicatorSnapshot

    result = await db.execute(
        select(Indicator).where(
            Indicator.update_strategy == "on_ai_analysis",
            Indicator.ai_extraction_key.isnot(None),
            Indicator.active.is_(True),
        )
    )
    indicators = list(result.scalars().all())
    now = datetime.now(UTC)
    count = 0

    for ind in indicators:
        key = ind.ai_extraction_key
        if key not in metrics:
            continue
        raw = metrics[key]
        value_numeric: Decimal | None = None
        value_text: str | None = None

        if ind.data_type == "quantitative":
            if raw is not None:
                value_numeric = Decimal(str(raw))
        else:
            value_text = str(raw) if raw is not None else None

        stmt = (
            pg_insert(IndicatorSnapshot)
            .values(
                indicator_id=ind.id,
                subject_type="asset",
                subject_id=asset_id,
                as_of_date=as_of_date,
                value_numeric=value_numeric,
                value_text=value_text,
                source="ai_analysis",
                source_ref=str(report_id),
                created_at=now,
            )
            .on_conflict_do_update(
                constraint="uq_snapshot_indicator_subject_date",
                set_={
                    "value_numeric": value_numeric,
                    "value_text": value_text,
                    "source": "ai_analysis",
                    "source_ref": str(report_id),
                },
            )
        )
        await db.execute(stmt)
        count += 1

    return count


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    from app.db.models.ai_report import AnalysisJob, AnalysisReport, UploadedFile

    now = datetime.now(UTC)
    report_date = date.fromisoformat(AI_RESULT["report_date"])

    async with SessionLocal() as db:
        # 1. UploadedFile (placeholder — 5 bytes mínimo para pasar la FK)
        uploaded = UploadedFile(
            id=uuid4(),
            user_id=USER_ID,
            holding_id=HOLDING_ID,
            original_filename="intel_q4_2026_simulated.pdf",
            mime_type="application/pdf",
            size_bytes=5,
            content=b"%PDF-",          # magic bytes válidos
        )
        db.add(uploaded)
        await db.flush()

        # 2. AnalysisJob (ya completado)
        job = AnalysisJob(
            id=uuid4(),
            holding_id=HOLDING_ID,
            uploaded_file_id=uploaded.id,
            provider=PROVIDER,
            model_version=MODEL_VERSION,
            status="succeeded",
            attempt_count=1,
            started_at=now,
            completed_at=now,
        )
        db.add(job)
        await db.flush()

        # 3. AnalysisReport
        report = AnalysisReport(
            id=uuid4(),
            holding_id=HOLDING_ID,
            uploaded_file_id=uploaded.id,
            analysis_job_id=job.id,
            report_date=report_date,
            provider=PROVIDER,
            model_version=MODEL_VERSION,
            extracted_metrics=AI_RESULT["metrics"],
            executive_summary=AI_RESULT["executive_summary"],
            global_signal=AI_RESULT["global_signal"],
            confidence_notes=AI_RESULT["confidence_notes"],
            raw_response={"text": json.dumps(AI_RESULT)},
        )
        db.add(report)
        await db.flush()

        # Enlazar job → report
        job.analysis_report_id = report.id

        # 4. IndicatorSnapshots
        asset_id = await _find_asset_id(db)
        snap_count = await _upsert_indicator_snapshots(
            db, asset_id, AI_RESULT["metrics"], report.id, report_date
        )

        await db.commit()

    print("=" * 60)
    print("INYECCIÓN COMPLETADA")
    print(f"  UploadedFile : {uploaded.id}")
    print(f"  AnalysisJob  : {job.id}")
    print(f"  AnalysisReport: {report.id}")
    print(f"  Indicadores   : {snap_count} snapshots upserted")
    print(f"  report_date   : {report_date}")
    print(f"  global_signal : {AI_RESULT['global_signal']}")
    print("=" * 60)
    print()
    print("Ahora ve a la pantalla de análisis del activo Intel en la app.")


if __name__ == "__main__":
    asyncio.run(main())
