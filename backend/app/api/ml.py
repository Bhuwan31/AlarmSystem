"""Machine-learning models: evaluation results and live advisory outlook (never issues warnings)."""
import httpx
from fastapi import APIRouter, HTTPException, Query

from app.ml import predict

router = APIRouter(prefix="/api/v1/ml", tags=["ml"])


def _models() -> dict:
    try:
        return predict.models()
    except predict.NotTrained as e:
        raise HTTPException(503, str(e)) from e


@router.get("/models")
async def models():
    """How each model was trained and how well it did on the held-out years (2023-2024)."""
    m = _models()
    return {"meta": m["meta"], "metrics": m["metrics"]}


@router.get("/outlook")
async def outlook():
    """Every model's prediction for each model station today."""
    _models()
    try:
        return await predict.outlook()
    except (httpx.HTTPError, RuntimeError) as e:
        raise HTTPException(502, f"live data unavailable: {e}") from e


@router.get("/outlook30")
async def outlook30():
    """30-day warning outlook: the warning agent stepped day by day through 51 ensemble river-flow futures."""
    _models()
    try:
        return await predict.outlook30()
    except (httpx.HTTPError, RuntimeError) as e:
        raise HTTPException(502, f"live data unavailable: {e}") from e


@router.get("/anomalies")
async def anomalies(hours: int = Query(48, ge=1, le=72)):
    """Gauge readings the Isolation Forest finds unusual."""
    _models()
    return await predict.anomalies(hours)
