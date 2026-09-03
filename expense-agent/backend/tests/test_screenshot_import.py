from datetime import date, datetime, timezone
from unittest.mock import patch

from app.schemas.expense_schema import ExpenseCreate
from app.services.expense_service import ExpenseService
from app.services.screenshot_import_service import ScreenshotImportService


def test_screenshot_skips_failed_and_adds_success(db):
    svc = ScreenshotImportService(db)
    extracted = {
        "transactions": [
            {
                "amount": 1,
                "merchant": "prathis",
                "status": "success",
                "direction": "debit",
                "date": None,
                "time_hint": "1 min ago",
            },
            {
                "amount": 30000,
                "merchant": "prathis",
                "status": "failed",
                "direction": "debit",
                "date": "2020-07-02",
            },
            {
                "amount": 49999,
                "merchant": "prathis",
                "status": "success",
                "direction": "debit",
                "date": "2020-07-02",
            },
        ]
    }
    with patch.object(svc, "_extract", return_value=extracted):
        result = svc.import_image(b"fake-image", filename="phonepe.png")

    assert result["ok"] is True
    assert result["failed_rows"] == 1
    merchants = [item["merchant"] for item in result["added"]]
    amounts = [item["amount"] for item in result["added"]]
    assert merchants == ["prathis", "prathis"]
    assert 1 in amounts
    assert 49999 in amounts
    assert 30000 not in amounts
    listed = ExpenseService(db).list_expenses()
    assert any(float(e.amount) == 49999 for e in listed)


def test_screenshot_skips_duplicate(db):
    ExpenseService(db).create(
        ExpenseCreate(
            amount=100,
            category="Personal",
            merchant="prathis",
            spent_at=datetime(2020, 7, 1, 12, 0, tzinfo=timezone.utc),
        ),
        source="manual",
    )
    db.commit()
    svc = ScreenshotImportService(db)
    extracted = {
        "transactions": [
            {
                "amount": 100,
                "merchant": "prathis",
                "status": "success",
                "direction": "debit",
                "date": "2020-07-01",
            }
        ]
    }
    with patch.object(svc, "_extract", return_value=extracted):
        result = svc.import_image(b"fake-image")
    assert result["added"] == []
    assert any(s.get("reason") == "duplicate" for s in result["skipped"])
