# API Documentation

Base URL: `http://localhost:8000`

## Health

`GET /health` → `{ "status": "ok" }`

## Payments

### `POST /api/payments/events`
Production-shaped ingest of a normalized payment event.

### `POST /api/payments/mock`
Dev mock for a single UPI/SMS/raw notification.

### `POST /api/payments/mock/pair`
Dev helper: ingest UPI + SMS for the same payment (correlated into one transaction).

### `GET /api/transactions`
List correlated transactions.

## Expenses

### `GET /api/expenses`
### `POST /api/expenses` — structured manual create
### `POST /api/expenses/nl` — natural language (`Spent ₹500 on movie`)
### `GET /api/expenses/{id}`
### `PATCH /api/expenses/{id}`

## Analytics

### `GET /api/analytics/summary?year=&month=`
Returns SQL totals + optional insight narration.

### `GET /api/categories`
Category taxonomy tree.

## Chat / clarifications

### `POST /api/chat`
```json
{ "message": "Car service", "clarification_id": 1 }
```

### `GET /api/notifications/pending`
Pending ask-user clarifications.

### `POST /api/clarifications/{id}/confirm`
Confirm or edit proposed category after clarification.
