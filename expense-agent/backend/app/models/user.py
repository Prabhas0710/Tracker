from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base

if TYPE_CHECKING:
    from app.models.expense import Expense
    from app.models.user_preference import MerchantMemory, UserPreference
    from app.models.meal_memory import MealMemory


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), default="Default User")
    email: Mapped[str] = mapped_column(String(255), unique=True, default="user@expense.local")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    expenses: Mapped[list["Expense"]] = relationship(back_populates="user")
    preferences: Mapped[list["UserPreference"]] = relationship(back_populates="user")
    merchant_memories: Mapped[list["MerchantMemory"]] = relationship(back_populates="user")
    meal_memories: Mapped[list["MealMemory"]] = relationship(back_populates="user")
