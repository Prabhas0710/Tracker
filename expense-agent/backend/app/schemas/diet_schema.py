from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

MealType = Literal["Breakfast", "Lunch", "Dinner", "Snack"]


class MealCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    meal_type: MealType = "Snack"
    calories: float = Field(ge=0, le=10000)
    protein: Optional[float] = Field(default=None, ge=0, le=1000)
    carbs: Optional[float] = Field(default=None, ge=0, le=1000)
    fat: Optional[float] = Field(default=None, ge=0, le=1000)
    fiber: Optional[float] = Field(default=None, ge=0, le=1000)
    notes: Optional[str] = Field(default=None, max_length=500)
    eaten_at: Optional[datetime] = None


class MealUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    meal_type: Optional[MealType] = None
    calories: Optional[float] = Field(default=None, ge=0, le=10000)
    protein: Optional[float] = Field(default=None, ge=0, le=1000)
    carbs: Optional[float] = Field(default=None, ge=0, le=1000)
    fat: Optional[float] = Field(default=None, ge=0, le=1000)
    fiber: Optional[float] = Field(default=None, ge=0, le=1000)
    notes: Optional[str] = Field(default=None, max_length=500)


class MealOut(BaseModel):
    id: int
    name: str
    meal_type: str
    calories: float
    protein: Optional[float] = None
    carbs: Optional[float] = None
    fat: Optional[float] = None
    fiber: Optional[float] = None
    notes: Optional[str] = None
    source: str
    eaten_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class MealNL(BaseModel):
    text: str = Field(..., min_length=1, examples=["Chicken biryani for lunch 650 kcal"])
    eaten_at: Optional[datetime] = None


class MealEstimateIn(BaseModel):
    food: str = Field(..., min_length=1, max_length=255, examples=["avocado (half)"])


class MealEstimateOut(BaseModel):
    name: str
    calories: float
    protein: float
    carbs: float
    fat: float
    fiber: float
    source: Literal["memory", "branded", "ai", "heuristic"] = "ai"


class DietGoalUpdate(BaseModel):
    calorie_goal: float = Field(gt=0, le=20000)
    protein_goal: Optional[float] = Field(default=None, ge=0, le=1000)


class DietDayOut(BaseModel):
    date: str
    calorie_goal: float
    protein_goal: float
    calories: float
    remaining: float
    protein: float
    protein_remaining: float
    carbs: float
    fat: float
    fiber: float
    meals: list[MealOut]


class DietMonthDayOut(BaseModel):
    date: str
    hit_goal: bool


class DietMonthOut(BaseModel):
    month: str
    streak_days: int
    grace_misses: int = 0
    streak_broken: bool = False
    streak_ended_length: Optional[int] = None
    days: list[DietMonthDayOut]
