# Architecture

```text
iPhone / Web (Next.js)
        │
        ▼
   FastAPI API
        │
        ▼
Payment Event Ingestion  ← mock / webhook / forwarded / future bank APIs
        │
        ▼
Transaction Service (normalize + correlate UPI + SMS)
        │
        ▼
LangGraph Expense Workflow
   ├── Memory Agent
   ├── Category Agent (OpenAI)
   └── Notification Agent
        │
   confidence >= threshold ──► save expense
   confidence < threshold  ──► ask user → learn → save
        │
        ▼
   PostgreSQL (source of financial truth)
        │
   Dashboard / Analytics / Chat
```

## Design principles

1. **Classify before asking** — never prompt the user when confidence is high.
2. **One payment → one expense** — correlate UPI + SMS by ref / amount / merchant / time.
3. **Configurable threshold** — `CLASSIFICATION_CONFIDENCE_THRESHOLD` (default `0.90`).
4. **Learn from answers** — merchant memory personalizes future auto-classification.
5. **DB is truth** — analytics amounts come from SQL aggregates, never LLM estimates.
6. **Ingestion abstraction** — no assumption that Safari can read device notifications.
