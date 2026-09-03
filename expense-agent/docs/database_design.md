# Database Design — Expense Agent

## Overview

PostgreSQL stores all financial truth. Agents never invent amounts; they read aggregates via tools.

## Tables

### users
Single default user (`id=1`) for MVP.

### categories / subcategories
Seeded taxonomy: Food, Groceries, Entertainment, Fuel, Transport, Shopping, Bills, Health, Other.

### payment_events
Raw normalized ingest from UPI notifications, bank SMS, webhooks, or manual forward.
- `source`, `amount`, `merchant`, `payment_method`, `transaction_id`, `upi_ref`, `raw_text`, `event_timestamp`
- Linked to correlated `transactions` via `correlated_transaction_id`

### transactions
Canonical payment after source correlation.
- `sources` JSON array (e.g. `["upi_notification","bank_sms"]`)
- `status`: `pending` → `classified` | `needs_user` → `saved`
- One transaction → at most one expense

### expenses
Saved spend rows. Amounts always from DB inserts, never LLM estimates.
- Optional `transaction_id` (null for pure manual entry)
- `source`: `auto` | `manual` | `chat`

### merchant_memories
Per-user learned merchant → category mappings with confidence and hit counts.

### merchant_priors
Soft global priors (PVR, Swiggy, Uber, …). Lower priority than user memory.

### user_preferences
Explicit user instruction overrides (`key` / `value`).

### clarification_requests
Pending ask-user prompts when confidence is below threshold.

### chat_messages
Conversation history for clarifications and NL expense entry.

## Correlation keys

Match on: exact `transaction_id` / `upi_ref`, else amount + fuzzy merchant + ±5 minute window.
