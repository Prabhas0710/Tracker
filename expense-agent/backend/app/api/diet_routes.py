from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.schemas.diet_schema import (
    DietDayOut,
    DietGoalUpdate,
    DietMonthOut,
    MealCreate,
    MealEstimateIn,
    MealEstimateOut,
    MealNL,
    MealOut,
    MealUpdate,
)
from app.services.diet_service import DietService

router = APIRouter(prefix="/api/diet", tags=["diet"])


@router.get("/day", response_model=DietDayOut)
def get_day(
    date: str | None = Query(default=None, description="YYYY-MM-DD in IST"),
    db: Session = Depends(get_db),
):
    return DietService(db).list_day(date)


@router.get("/month", response_model=DietMonthOut)
def get_month(
    month: str = Query(..., description="YYYY-MM in IST"),
    db: Session = Depends(get_db),
):
    return DietService(db).list_month(month)


@router.post("/estimate", response_model=MealEstimateOut)
def estimate_meal(payload: MealEstimateIn, db: Session = Depends(get_db)):
    return DietService(db).estimate(payload.food)


@router.post("/meals", response_model=MealOut)
def create_meal(payload: MealCreate, db: Session = Depends(get_db)):
    meal = DietService(db).create(payload)
    db.commit()
    db.refresh(meal)
    return DietService.to_out(meal)


@router.post("/meals/nl")
def create_meal_nl(payload: MealNL, db: Session = Depends(get_db)):
    meal, reply = DietService(db).create_from_nl(payload)
    db.commit()
    db.refresh(meal)
    return {"reply": reply, "meal": DietService.to_out(meal)}


@router.patch("/meals/{meal_id}", response_model=MealOut)
def update_meal(meal_id: int, payload: MealUpdate, db: Session = Depends(get_db)):
    meal = DietService(db).update(meal_id, payload)
    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")
    db.commit()
    db.refresh(meal)
    return DietService.to_out(meal)


@router.delete("/meals/{meal_id}")
def delete_meal(meal_id: int, db: Session = Depends(get_db)):
    if not DietService(db).delete(meal_id):
        raise HTTPException(status_code=404, detail="Meal not found")
    db.commit()
    return {"deleted": True}


@router.post("/goal")
def set_goal(payload: DietGoalUpdate, db: Session = Depends(get_db)):
    result = DietService(db).set_goal(payload.calorie_goal, payload.protein_goal)
    db.commit()
    return result
