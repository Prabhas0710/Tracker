export type Expense = {
  id: number;
  amount: number;
  merchant: string | null;
  category: string;
  subcategory: string | null;
  description: string | null;
  confidence: number | null;
  source: string;
  direction?: "debit" | "credit" | "transfer";
  spent_at: string;
  transaction_id: number | null;
  upi_ref?: string | null;
  reference_id?: string | null;
  payment_method?: string | null;
  card_issuer?: string | null;
  account_suffix?: string | null;
  created_at: string;
};
