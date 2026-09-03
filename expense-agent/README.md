# Ledgerly — Expense Agent

Automatic payment understanding for UPI notifications and bank SMS, with AI classification **before** asking the user.

## Stack

- **Backend:** FastAPI, LangGraph, OpenAI, SQLAlchemy
- **Database:** PostgreSQL + pgAdmin
- **Frontend:** Next.js (mobile-first, iPhone Safari)

## Quick start

### 1. Start Postgres + pgAdmin

```bash
cd expense-agent
docker compose up -d postgres pgadmin
```

- Postgres: `localhost:5434` (mapped from container `5432`)
- pgAdmin: http://localhost:5050  
  - Email: `admin@expense.local`  
  - Password: `admin`  
  - Add server host `postgres`, user/password/db: `expense` / `expense` / `expense_agent`

> Host port is **5434** because 5432/5433 are often already taken locally.

### 2. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set OPENAI_API_KEY
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

App: http://localhost:3000

## Mock payment flow (dev)

High confidence (auto-save):

```bash
curl -X POST http://localhost:8000/api/payments/mock/pair \
  -H 'Content-Type: application/json' \
  -d '{
    "upi": {
      "source": "upi_notification",
      "raw_text": "₹450 paid to PVR Cinemas via UPI",
      "amount": 450,
      "merchant": "PVR Cinemas",
      "transaction_id": "123456789"
    },
    "sms": {
      "source": "bank_sms",
      "raw_text": "INR 450.00 debited from A/c XX1234 UPI Ref: 123456789 To: PVR Cinemas",
      "amount": 450,
      "merchant": "PVR Cinemas",
      "upi_ref": "123456789"
    }
  }'
```

Low confidence (asks user):

```bash
curl -X POST http://localhost:8000/api/payments/mock \
  -H 'Content-Type: application/json' \
  -d '{
    "source": "upi_notification",
    "raw_text": "₹1800 paid to ABC Services via UPI",
    "amount": 1800,
    "merchant": "ABC Services"
  }'
```

Then answer via chat:

```bash
curl -X POST http://localhost:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Car service"}'
```

## Tests

```bash
cd backend
PYTHONPATH=. pytest -q
```

## Docs

- [Architecture](docs/architecture.md)
- [Agent flow](docs/agent_flow.md)
- [Database design](docs/database_design.md)
- [API documentation](docs/api_documentation.md)

## Important constraint

A Safari web app **cannot** read iPhone notifications/SMS directly. This project uses a **Payment Event Ingestion Layer** with a mock API so the full AI workflow can be built before connecting real, legally supported sources.
