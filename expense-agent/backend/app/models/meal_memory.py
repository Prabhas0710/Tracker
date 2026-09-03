from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class MealMemory(Base):
    __tablename__ = "meal_memories"
    __table_args__ = (UniqueConstraint("user_id", "meal_key", name="uq_user_meal_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    meal_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    meal_display: Mapped[str] = mapped_column(String(255), nullable=False)
    calories: Mapped[float] = mapped_column(Float, nullable=False)
    protein: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    carbs: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fiber: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hit_count: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="meal_memories")
