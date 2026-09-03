from app.schemas.expense_schema import ExpenseCreate
from app.services.assistant_service import AssistantService
from app.services.expense_service import ExpenseService


def test_recategorize_merchant_updates_latest(db):
    ExpenseService(db).create(
        ExpenseCreate(amount=1432, category="Other", merchant="Myntra Designs Pvt Ltd"),
        source="test",
    )
    db.commit()
    bot = AssistantService(db)
    result = bot.run_tool(
        "recategorize_merchant",
        {"merchant": "Myntra", "category": "Shopping"},
    )
    db.commit()
    assert result["count"] == 1
    assert result["updated"][0]["category"] == "Shopping"


def test_set_diet_goals_from_bot(db):
    bot = AssistantService(db)
    result = bot.run_tool("set_diet_goals", {"calorie_goal": 2000, "protein_goal": 140})
    db.commit()
    assert result["calorie_goal"] == 2000
    assert result["protein_goal"] == 140
