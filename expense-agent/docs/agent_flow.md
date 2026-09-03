# Agent Flow

## Automatic path

1. `receive_transaction`
2. `normalize_transaction`
3. `correlate_payment_sources`
4. `lookup_memory` (preference → user memory → soft prior)
5. `classify_category` (semantic OpenAI / offline known merchants / rules)
6. `check_confidence`
7. If high → `save_expense` → `update_dashboard`
8. If low → `ask_user` (persist clarification) and stop

## Clarification path

1. User answers in chat (`POST /api/chat`)
2. `process_user_response`
3. `learn_preference` (merchant memory)
4. `save_expense`
5. `update_dashboard`

## Classification priority

1. Explicit user instruction / preference  
2. User-specific merchant memory  
3. Combined UPI + SMS context  
4. Merchant / VPA prior  
5. Semantic AI classification  
6. Generic category rules  
7. Ask user  

## Agents

| Agent | Responsibility |
|-------|----------------|
| ExpenseAgent | Orchestrates graph + NL manual entry + clarification resume |
| CategoryAgent | Category / subcategory / confidence |
| MemoryAgent | Merchant history + learning |
| NotificationAgent | Clarification / confirmation copy |
| AnalyticsAgent | Insights over tool-fetched DB totals only |
