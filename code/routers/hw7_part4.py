import os
import tempfile
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from langchain_core.language_models.chat_models import BaseChatModel

from hw7_part4_agent import (
    MAX_UPLOAD_BYTES,
    Part4AgentError,
    create_real_model,
    run_part4_agent,
)
from hw7_part4_schemas import Part4AnalyzeResponse
from models import User
from routers.auth import get_current_user

router = APIRouter(
    prefix="/api/hw7/part4",
    tags=["HW7 Part 4 Bike Membership Advisor"],
)


def get_part4_model() -> BaseChatModel:
    """Dependency seam used by offline tests; production uses fixed Ollama."""

    return create_real_model()


def _http_error(exc: Part4AgentError) -> HTTPException:
    if exc.stop_reason == "upload_too_large":
        code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    elif exc.stop_reason in {"validation_error"}:
        code = status.HTTP_422_UNPROCESSABLE_ENTITY
    elif exc.stop_reason in {
        "tool_call_budget_exhausted",
        "wall_clock_budget_exhausted",
        "recursion_limit",
    }:
        code = status.HTTP_504_GATEWAY_TIMEOUT
    else:
        code = status.HTTP_502_BAD_GATEWAY
    return HTTPException(
        status_code=code,
        detail={"message": str(exc), "stop_reason": exc.stop_reason},
    )


@router.post("/analyze", response_model=Part4AnalyzeResponse)
async def analyze_bike_membership(
    csv_file: Annotated[UploadFile, File(description="Bay Wheels trip CSV")],
    pricing_url: Annotated[str, Form()],
    _user: User = Depends(get_current_user),
    model: BaseChatModel = Depends(get_part4_model),
) -> dict[str, Any]:
    """Analyze one bounded upload; all authenticated roles may use it."""

    if not csv_file.filename or not csv_file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A .csv upload is required",
        )

    path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix="hw7-part4-",
            suffix=".csv",
            delete=False,
        ) as output:
            path = Path(output.name)
            size = 0
            while chunk := await csv_file.read(65_536):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise Part4AgentError(
                        f"Uploaded CSV exceeds the {MAX_UPLOAD_BYTES}-byte limit",
                        stop_reason="upload_too_large",
                    )
                output.write(chunk)

        return run_part4_agent(
            csv_path=path,
            pricing_url=pricing_url,
            model=model,
        )
    except Part4AgentError as exc:
        raise _http_error(exc) from exc
    finally:
        await csv_file.close()
        if path is not None:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
