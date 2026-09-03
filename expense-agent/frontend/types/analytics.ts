export type AnalyticsSummary = {
  year: number;
  month: number;
  label: string;
  total_spent: number;
  total_debits?: number;
  total_credits?: number;
  total_transfers?: number;
  net?: number;
  by_category: { category: string; amount: number }[];
  by_credit_category?: { category: string; amount: number }[];
  credit_card_spent?: number;
  credit_card_due?: number;
  credit_card_banks?: Record<
    string,
    {
      bank?: string;
      cycle_start_at?: string | null;
      bill_paid_at?: string | null;
      bill_amount?: number | null;
      card_suffix?: string | null;
      cycle_spent?: number;
      due_amount?: number;
    }
  >;
  credit_card_cycle?: {
    cycle_start_at?: string | null;
    bill_paid_at?: string | null;
    bill_amount?: number | null;
    card_suffix?: string | null;
    banks?: Record<
      string,
      {
        bank?: string;
        cycle_start_at?: string | null;
        bill_paid_at?: string | null;
        bill_amount?: number | null;
        card_suffix?: string | null;
      }
    >;
  };
  currency: string;
  insight?: string;
  period?: "day" | "week" | "month" | "year";
  date?: string | null;
  start?: string;
  end?: string;
  top_category?: string | null;
  top_category_amount?: number;
  diet?: DietAnalytics;
};

export type DietAnalytics = {
  period: string;
  label: string;
  calorie_goal: number;
  protein_goal: number;
  days_in_range: number;
  hit_days: number;
  missed_days: number;
  logged_days: number;
  no_log_days: number;
  hit_dates: string[];
  missed_dates: string[];
  no_log_dates: string[];
  insight: string;
  day?: {
    date: string;
    calorie_goal: number;
    protein_goal: number;
    calories: number;
    protein: number;
    remaining: number;
    protein_remaining: number;
    hit_goal?: boolean;
    meals?: unknown[];
  } | null;
};

export type Clarification = {
  id: number;
  transaction_id: number;
  prompt_message: string;
  status: string;
  amount?: number | null;
  merchant?: string | null;
  expense_id?: number | null;
  current_category?: string | null;
  proposed_category?: string | null;
  proposed_subcategory?: string | null;
  proposed_description?: string | null;
  user_response?: string | null;
  created_at: string;
};

export type ChatResponse = {
  reply: string;
  clarification_id?: number | null;
  expense_id?: number | null;
  conversation_id?: number | null;
  needs_confirm?: boolean;
  proposed?: Record<string, unknown> | null;
  dashboard_hint?: AnalyticsSummary | null;
};

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  created_at?: string | null;
};

export type ChatConversation = {
  id: number;
  title: string;
  preview: string;
  created_at: string;
  updated_at: string;
  message_count: number;
};

export type ChatConversationDetail = ChatConversation & {
  messages: ChatMessage[];
};
