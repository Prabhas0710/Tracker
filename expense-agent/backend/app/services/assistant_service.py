"""Ledgerly chat bot: answers questions about spend/diet and applies edits."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from openai import OpenAI
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models import ChatMessage, Expense
from app.schemas.chat_schema import ChatResponse
from app.services.chat_history_service import ChatHistoryService
from app.schemas.diet_schema import MealCreate
from app.schemas.expense_schema import ExpenseUpdate
from app.services.analytics_service import AnalyticsService
from app.services.category_service import CategoryService
from app.services.diet_service import DietService, today_ist
from app.services.expense_service import ExpenseService

logger = get_logger(__name__)

SYSTEM = """You are Ledgerly, Prabhas's personal finance and diet assistant.
You speak like a calm, capable human assistant — warm but concise.
You can look up real expenses and meals, answer questions, and make edits they request.
Use tools before guessing numbers. Never invent amounts.
When they ask to recategorize, rename, delete, log, or change a goal, call the matching tool.
After a successful edit, confirm what you changed in one short sentence.
Indian rupees. Dates are IST.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_spend_summary",
            "description": "Month spend totals by category.",
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {"type": "integer"},
                    "month": {"type": "integer", "description": "1-12"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_expenses",
            "description": "Search recent expenses by merchant or category.",
            "parameters": {
                "type": "object",
                "properties": {
                    "merchant": {"type": "string"},
                    "category": {"type": "string"},
                    "limit": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_expense",
            "description": "Edit one expense by id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expense_id": {"type": "integer"},
                    "category": {"type": "string"},
                    "merchant": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["expense_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recategorize_merchant",
            "description": "Change category for expenses matching a merchant name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "merchant": {"type": "string"},
                    "category": {"type": "string"},
                    "all_matches": {"type": "boolean"},
                },
                "required": ["merchant", "category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_expense",
            "description": "Create an expense from a natural language line like Spent 500 on Uber.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_diet_day",
            "description": "Calories and meals for a day (YYYY-MM-DD IST).",
            "parameters": {
                "type": "object",
                "properties": {"date": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_meal",
            "description": "Log a meal from food text. Estimates nutrition if needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "food": {"type": "string"},
                    "meal_type": {
                        "type": "string",
                        "enum": ["Breakfast", "Lunch", "Dinner", "Snack"],
                    },
                    "date": {"type": "string"},
                },
                "required": ["food"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_meal",
            "description": "Delete a meal by id.",
            "parameters": {
                "type": "object",
                "properties": {"meal_id": {"type": "integer"}},
                "required": ["meal_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_diet_goals",
            "description": "Update daily calorie and/or protein goals.",
            "parameters": {
                "type": "object",
                "properties": {
                    "calorie_goal": {"type": "number"},
                    "protein_goal": {"type": "number"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_categories",
            "description": "List spend category names.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


class AssistantService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def history(self, limit: int = 40, conversation_id: int | None = None) -> list[dict[str, str]]:
        chats = ChatHistoryService(self.db)
        if conversation_id:
            return chats.conversation_messages(conversation_id)
        latest = chats.list_conversations()
        if latest:
            return chats.conversation_messages(latest[0].id)
        rows = (
            self.db.query(ChatMessage)
            .filter(ChatMessage.user_id == self.settings.default_user_id)
            .order_by(ChatMessage.id.desc())
            .limit(limit)
            .all()
        )
        rows.reverse()
        return [
            {"role": row.role, "content": row.content}
            for row in rows
            if row.role in {"user", "assistant"}
        ]

    def reply(self, message: str, conversation_id: int | None = None) -> ChatResponse:
        user_id = self.settings.default_user_id
        chats = ChatHistoryService(self.db)
        conv = chats.ensure_conversation(conversation_id, title_from=message, user_id=user_id)
        self.db.add(
            ChatMessage(
                user_id=user_id,
                conversation_id=conv.id,
                role="user",
                content=message,
            )
        )
        self.db.flush()
        text = self._complete(message)
        self.db.add(
            ChatMessage(
                user_id=user_id,
                conversation_id=conv.id,
                role="assistant",
                content=text,
            )
        )
        chats.touch(conv, title_from=message)
        self.db.commit()
        return ChatResponse(reply=text, conversation_id=conv.id)

    def _complete(self, message: str) -> str:
        if not self.settings.openai_api_key:
            return self._fallback(message)
        client = OpenAI(api_key=self.settings.openai_api_key)
        now = datetime.now()
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM},
            {
                "role": "system",
                "content": f"Today is {today_ist()} IST. Current month is {now.year}-{now.month:02d}.",
            },
            {"role": "user", "content": message},
        ]
        for _ in range(6):
            try:
                response = client.chat.completions.create(
                    model=self.settings.openai_chat_model or self.settings.openai_model,
                    temperature=0,
                    tools=TOOLS,
                    messages=messages,
                )
            except Exception as extra:  # noqa: BLE001
                logger.warning("Assistant call failed: %s", extra)
                return self._fallback(message)
            choice = response.choices[0]
            tool_calls = choice.message.tool_calls or []
            if not tool_calls:
                return (choice.message.content or "").strip() or "Done."
            messages.append(
                {
                    "role": "assistant",
                    "content": choice.message.content or "",
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.function.name,
                                "arguments": call.function.arguments,
                            },
                        }
                        for call in tool_calls
                    ],
                }
            )
            for call in tool_calls:
                args = json.loads(call.function.arguments or "{}")
                result = self.run_tool(call.function.name, args)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result, default=str),
                    }
                )
        return "I looked that up, but need a clearer request to finish."

    def run_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        try:
            if name == "get_spend_summary":
                now = datetime.now()
                year = int(args.get("year") or now.year)
                month = int(args.get("month") or now.month)
                summary = AnalyticsService(self.db).monthly_summary(year, month)
                return {
                    "year": year,
                    "month": month,
                    "total_debits": summary.get("total_debits") or summary.get("total_spent"),
                    "total_credits": summary.get("total_credits"),
                    "by_category": summary.get("by_category", [])[:12],
                }
            if name == "list_expenses":
                return {"expenses": self._search_expenses(args)}
            if name == "update_expense":
                return self._update_expense(args)
            if name == "recategorize_merchant":
                return self._recategorize_merchant(args)
            if name == "log_expense":
                return self._log_expense(str(args.get("text") or ""))
            if name == "get_diet_day":
                day = DietService(self.db).list_day(args.get("date"))
                meals = [
                    {
                        "id": meal.id,
                        "name": meal.name,
                        "meal_type": meal.meal_type,
                        "calories": meal.calories,
                        "protein": meal.protein,
                    }
                    for meal in day["meals"]
                ]
                return {
                    "date": day["date"],
                    "calories": day["calories"],
                    "calorie_goal": day["calorie_goal"],
                    "protein": day["protein"],
                    "protein_goal": day["protein_goal"],
                    "meals": meals,
                }
            if name == "log_meal":
                return self._log_meal(args)
            if name == "delete_meal":
                ok = DietService(self.db).delete(int(args["meal_id"]))
                self.db.flush()
                return {"deleted": ok, "meal_id": args.get("meal_id")}
            if name == "set_diet_goals":
                diet = DietService(self.db)
                calorie = args.get("calorie_goal") or diet.get_goal()
                protein = args.get("protein_goal")
                result = diet.set_goal(float(calorie), float(protein) if protein is not None else None)
                self.db.flush()
                return result
            if name == "list_categories":
                return {"categories": CategoryService(self.db).list_names()}
        except Exception as extra:  # noqa: BLE001
            logger.warning("Tool %s failed: %s", name, extra)
            return {"error": str(extra)}
        return {"error": f"Unknown tool {name}"}

    def _search_expenses(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        limit = min(int(args.get("limit") or 12), 30)
        query = self.db.query(Expense).filter(Expense.user_id == self.settings.default_user_id)
        merchant = (args.get("merchant") or "").strip()
        category = (args.get("category") or "").strip()
        if merchant:
            query = query.filter(func.lower(Expense.merchant).like(f"%{merchant.lower()}%"))
        if category:
            query = query.filter(func.lower(Expense.category) == category.lower())
        rows = query.order_by(Expense.spent_at.desc()).limit(limit).all()
        return [
            {
                "id": row.id,
                "amount": float(row.amount),
                "merchant": row.merchant,
                "category": row.category,
                "spent_at": row.spent_at.astimezone().strftime("%Y-%m-%d") if row.spent_at else None,
            }
            for row in rows
        ]

    def _update_expense(self, args: dict[str, Any]) -> dict[str, Any]:
        payload = ExpenseUpdate(
            category=args.get("category"),
            merchant=args.get("merchant"),
            description=args.get("description"),
        )
        expense = ExpenseService(self.db).update(int(args["expense_id"]), payload)
        if not expense:
            return {"error": "Expense not found"}
        self.db.flush()
        return {
            "id": expense.id,
            "amount": float(expense.amount),
            "merchant": expense.merchant,
            "category": expense.category,
        }

    def _recategorize_merchant(self, args: dict[str, Any]) -> dict[str, Any]:
        merchant = str(args["merchant"]).strip()
        category = str(args["category"]).strip()
        matches = self._search_expenses({"merchant": merchant, "limit": 20})
        if not matches:
            return {"error": f"No expenses found for {merchant}"}
        ids = [row["id"] for row in matches] if args.get("all_matches") else [matches[0]["id"]]
        updated = []
        for expense_id in ids:
            result = self._update_expense({"expense_id": expense_id, "category": category})
            if "error" not in result:
                updated.append(result)
        return {"updated": updated, "count": len(updated)}

    def _log_expense(self, text: str) -> dict[str, Any]:
        import re
        from datetime import timezone

        from app.agents.category_agent import CategoryAgent
        from app.agents.memory_agent import MemoryAgent
        from app.schemas.expense_schema import ExpenseCreate
        from app.services.payment_parser import parse_payment_text

        amount = None
        merchant = None
        try:
            parsed = parse_payment_text(text, source="manual")
            amount = parsed["amount"]
            merchant = parsed.get("merchant")
        except ValueError:
            match = re.search(
                r"(?:₹|INR|Rs\.?)?\s*([0-9]{1,3}(?:,[0-9]{2,3})*(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)",
                text,
                re.I,
            )
            if match:
                amount = float(match.group(1).replace(",", ""))
        if amount is None:
            return {"error": "Need an amount to log an expense."}
        classified = CategoryAgent(self.db).parse_user_response(text, merchant=merchant, amount=amount)
        expense = ExpenseService(self.db).create(
            ExpenseCreate(
                amount=amount,
                category=classified.get("category") or "Other",
                subcategory=classified.get("subcategory"),
                description=classified.get("description") or text,
                merchant=merchant,
                spent_at=datetime.now(timezone.utc),
            ),
            source="chat",
        )
        if merchant:
            MemoryAgent(self.db).learn(
                merchant=merchant,
                category=expense.category,
                subcategory=expense.subcategory,
            )
        self.db.flush()
        return {
            "id": expense.id,
            "amount": float(expense.amount),
            "merchant": expense.merchant,
            "category": expense.category,
        }

    def _log_meal(self, args: dict[str, Any]) -> dict[str, Any]:
        food = str(args.get("food") or "").strip()
        meal_type = args.get("meal_type") or "Snack"
        date = args.get("date") or today_ist()
        diet = DietService(self.db)
        estimate = diet.estimate(food)
        meal = diet.create(
            MealCreate(
                name=food,
                meal_type=meal_type,
                calories=estimate.calories,
                protein=estimate.protein,
                carbs=estimate.carbs,
                fat=estimate.fat,
                fiber=estimate.fiber,
                eaten_at=datetime.fromisoformat(f"{date}T12:00:00+05:30"),
            ),
            source="chat",
        )
        self.db.flush()
        return {
            "id": meal.id,
            "name": meal.name,
            "meal_type": meal.meal_type,
            "calories": meal.calories,
            "protein": meal.protein,
        }

    def _fallback(self, message: str) -> str:
        lower = message.lower()
        if any(word in lower for word in ("spent", "spend", "expense", "how much")):
            now = datetime.now()
            data = self.run_tool("get_spend_summary", {"year": now.year, "month": now.month})
            total = data.get("total_debits") or 0
            return f"This month you have spent ₹{float(total):,.0f}."
        if "calorie" in lower or "protein" in lower or "diet" in lower or "meal" in lower:
            day = self.run_tool("get_diet_day", {})
            return (
                f"Today you have {day.get('calories')} kcal "
                f"(goal {day.get('calorie_goal')}) and {day.get('protein')} g protein "
                f"(goal {day.get('protein_goal')})."
            )
        return (
            "Ask me about your spend or diet, or tell me what to change — "
            "for example: recategorize Myntra to Shopping."
        )
