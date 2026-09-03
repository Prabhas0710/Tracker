export type Transaction = {
  id: number;
  amount: number;
  merchant: string | null;
  payment_method: string | null;
  external_transaction_id: string | null;
  upi_ref: string | null;
  sources: string[];
  status: string;
  event_timestamp: string;
  raw_texts: string[];
  expense_id?: number | null;
  clarification_id?: number | null;
  category?: string | null;
  subcategory?: string | null;
  confidence?: number | null;
  message?: string | null;
};

export type IngestResult = {
  transaction: Transaction;
  created_new: boolean;
  merged: boolean;
  classification?: Record<string, unknown> | null;
};
