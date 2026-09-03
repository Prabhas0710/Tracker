from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.agents.expense_agent import ExpenseAgent
from app.database.database import get_db
from app.schemas.expense_schema import (
    ExpenseCreate,
    ExpenseOut,
    ExpenseUpdate,
    ManualExpenseNL,
)
from app.services.expense_service import ExpenseService
from app.services.screenshot_import_service import ScreenshotImportService

router = APIRouter(prefix="/api/expenses", tags=["expenses"])


@router.get("", response_model=list[ExpenseOut])
def list_expenses(
    limit: int = Query(default=500, ge=1, le=1000),
    year: int | None = Query(default=None),
    month: int | None = Query(default=None, ge=1, le=12),
    db: Session = Depends(get_db),
):
    return ExpenseService(db).list_expenses(limit=limit, year=year, month=month)


@router.post("", response_model=ExpenseOut)
def create_expense(payload: ExpenseCreate, db: Session = Depends(get_db)):
    expense = ExpenseService(db).create(payload, source="manual")
    db.commit()
    db.refresh(expense)
    return ExpenseService(db).to_out(expense)


@router.post("/from-image")
async def create_expenses_from_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    data = await file.read()
    if len(data) > 12 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image too large (max 12MB)")
    try:
        result = ScreenshotImportService(db).import_image(
            data,
            filename=file.filename or "screenshot.png",
            content_type=file.content_type or "image/png",
        )
    except Exception as extra:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Could not read image: {extra}") from extra
    return result


@router.post("/nl", response_model=dict)
def create_expense_nl(payload: ManualExpenseNL, db: Session = Depends(get_db)):
    result = ExpenseAgent(db).create_manual_from_nl(payload.text)
    return result.model_dump()


@router.patch("/{expense_id}", response_model=ExpenseOut)
def update_expense(expense_id: int, payload: ExpenseUpdate, db: Session = Depends(get_db)):
    expense = ExpenseService(db).update(expense_id, payload)
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    db.commit()
    db.refresh(expense)
    return ExpenseService(db).to_out(expense)


@router.get("/{expense_id}", response_model=ExpenseOut)
def get_expense(expense_id: int, db: Session = Depends(get_db)):
    expense = ExpenseService(db).get(expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    return ExpenseService(db).to_out(expense)
