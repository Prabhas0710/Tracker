import type {
  AnalyticsSummary,
  ChatConversation,
  ChatConversationDetail,
  ChatMessage,
  ChatResponse,
  Clarification,
} from "@/types/analytics";
import type { DietDay, DietMonth, Meal, MealEstimate } from "@/types/diet";
import type { Expense } from "@/types/expense";
import type { IngestResult, Transaction } from "@/types/transaction";

const API_PORT = "9843";

/** Same origin as the page; Next.js proxies /api to the backend. */
function apiBaseUrl(): string {
  if (typeof window !== "undefined") {
    return "";
  }
  return process.env.NEXT_PUBLIC_API_URL || `http://127.0.0.1:${API_PORT}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers || {});
  const hasBody = init?.body != null && init.body !== "";
  if (hasBody && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(`${apiBaseUrl()}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  getSummary: (
    year?: number,
    month?: number,
    opts?: { period?: "day" | "week" | "month" | "year"; date?: string },
  ) => {
    const params = new URLSearchParams();
    if (year) params.set("year", String(year));
    if (month) params.set("month", String(month));
    if (opts?.period) params.set("period", opts.period);
    if (opts?.date) params.set("date", opts.date);
    const qs = params.toString();
    return request<AnalyticsSummary>(`/api/analytics/summary${qs ? `?${qs}` : ""}`);
  },
  getExpenses: (year?: number, month?: number) => {
    const params = new URLSearchParams();
    if (year) params.set("year", String(year));
    if (month) params.set("month", String(month));
    const qs = params.toString();
    return request<Expense[]>(`/api/expenses${qs ? `?${qs}` : ""}`);
  },
  getTransactions: () => request<Transaction[]>("/api/transactions"),
  getPending: () => request<Clarification[]>("/api/notifications/pending"),
  chat: (message: string, clarification_id?: number, conversation_id?: number) =>
    request<ChatResponse>("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message, clarification_id, conversation_id }),
    }),
  getChatHistory: (conversation_id?: number) => {
    const qs = conversation_id ? `?conversation_id=${conversation_id}` : "";
    return request<ChatMessage[]>(`/api/chat/history${qs}`);
  },
  getChatConversations: () => request<ChatConversation[]>("/api/chat/conversations"),
  getChatConversation: (id: number) =>
    request<ChatConversationDetail>(`/api/chat/conversations/${id}`),
  deleteChatConversation: (id: number) =>
    request<{ deleted: boolean }>(`/api/chat/conversations/${id}`, { method: "DELETE" }),
  ensureChatBriefing: () =>
    request<{ message: string | null; shown: boolean }>("/api/chat/briefing"),
  confirmClarification: (
    id: number,
    body: {
      confirmed?: boolean;
      category?: string;
      subcategory?: string;
      description?: string;
    },
  ) =>
    request<ChatResponse>(`/api/clarifications/${id}/confirm`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  createExpense: (body: {
    amount: number;
    category: string;
    subcategory?: string;
    description?: string;
    merchant?: string;
  }) =>
    request<Expense>("/api/expenses", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  createExpenseNL: (text: string) =>
    request<ChatResponse>("/api/expenses/nl", {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
  updateExpense: (
    id: number,
    body: {
      category?: string;
      subcategory?: string | null;
      description?: string | null;
      merchant?: string | null;
      direction?: "debit" | "credit" | "transfer";
    },
  ) =>
    request<Expense>(`/api/expenses/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  deleteExpense: (id: number) =>
    request<{ deleted: boolean; id: number }>(`/api/expenses/${id}`, {
      method: "DELETE",
    }),
  markCreditCardPaid: (
    bank: "ICICI" | "HDFC",
    body?: { paid_at?: string; amount?: number },
  ) =>
    request<{
      bank: string;
      statement_day?: number;
      cycle_start_at?: string | null;
      bill_paid_at?: string | null;
      bill_amount?: number | null;
      marked_amount?: number;
    }>(`/api/credit-cards/${bank}/mark-paid`, {
      method: "POST",
      body: JSON.stringify(body || {}),
    }),
  mockPayment: (body: Record<string, unknown>) =>
    request<IngestResult>("/api/payments/mock", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  mockPaymentPair: (upi: Record<string, unknown>, sms: Record<string, unknown>) =>
    request<IngestResult>("/api/payments/mock/pair", {
      method: "POST",
      body: JSON.stringify({ upi, sms }),
    }),
  gmailStatus: () =>
    request<{
      connected: boolean;
      needs_reconnect?: boolean;
      count?: number;
      healthy_count?: number;
      email?: string | null;
      accounts?: Array<{
        id: number;
        email: string;
        has_refresh_token?: boolean;
        token_expiry?: string | null;
        ok?: boolean;
        needs_reconnect?: boolean;
        error?: string | null;
      }>;
    }>("/api/auth/gmail/status"),
  gmailSync: (email?: string) => {
    const qs = email ? `?email=${encodeURIComponent(email)}` : "";
    return request<{
      scanned: number;
      ingested: number;
      skipped: number;
      failed: number;
      retried?: number;
      results: Array<Record<string, unknown>>;
      accounts?: Array<Record<string, unknown>>;
      dashboard_total?: number;
      pending_clarifications?: number;
      message?: string;
      busy?: boolean;
    }>(`/api/auth/gmail/sync${qs}`, { method: "POST" });
  },
  gmailDisconnect: (email?: string) =>
    request<{ disconnected: boolean }>("/api/auth/gmail/disconnect", {
      method: "POST",
      body: JSON.stringify(email ? { email } : {}),
    }),
  gmailLoginUrl: () => "/api/auth/gmail/login",
  gmailReconnect: () =>
    request<{ login_url: string; cleared: string[] }>("/api/auth/gmail/reconnect", {
      method: "POST",
    }),
  transcribeAudio: async (blob: Blob, filename = "audio.webm") => {
    const body = new FormData();
    body.append("file", blob, filename);
    const res = await fetch(`${apiBaseUrl()}/api/voice/transcribe`, {
      method: "POST",
      body,
      cache: "no-store",
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || `Transcribe failed: ${res.status}`);
    }
    return res.json() as Promise<{ text: string }>;
  },
  importExpensesFromImage: async (blob: Blob, filename = "screenshot.png") => {
    const body = new FormData();
    body.append("file", blob, filename);
    const res = await fetch(`${apiBaseUrl()}/api/expenses/from-image`, {
      method: "POST",
      body,
      cache: "no-store",
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || `Image import failed: ${res.status}`);
    }
    return res.json() as Promise<{
      ok: boolean;
      reply: string;
      added: Array<{
        id: number;
        amount: number;
        merchant: string;
        category: string;
        spent_at: string;
      }>;
      skipped: Array<Record<string, unknown>>;
      failed_rows: number;
    }>;
  },
  getCategoryNames: () => request<string[]>("/api/categories/names"),
  getDietDay: (date?: string) => {
    const qs = date ? `?date=${encodeURIComponent(date)}` : "";
    return request<DietDay>(`/api/diet/day${qs}`);
  },
  getDietMonth: (month: string) =>
    request<DietMonth>(`/api/diet/month?month=${encodeURIComponent(month)}`),
  createMeal: (body: {
    name: string;
    meal_type: string;
    calories: number;
    protein?: number | null;
    carbs?: number | null;
    fat?: number | null;
    fiber?: number | null;
    eaten_at?: string;
  }) =>
    request<Meal>("/api/diet/meals", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  estimateMeal: (food: string) =>
    request<MealEstimate>("/api/diet/estimate", {
      method: "POST",
      body: JSON.stringify({ food }),
    }),
  createMealNL: (text: string, eaten_at?: string) =>
    request<{ reply: string; meal: Meal }>("/api/diet/meals/nl", {
      method: "POST",
      body: JSON.stringify({ text, eaten_at }),
    }),
  deleteMeal: (id: number) =>
    request<{ deleted: boolean }>(`/api/diet/meals/${id}`, { method: "DELETE" }),
  setDietGoal: (calorie_goal: number, protein_goal?: number) =>
    request<{ calorie_goal: number; protein_goal: number }>("/api/diet/goal", {
      method: "POST",
      body: JSON.stringify({ calorie_goal, protein_goal }),
    }),
};
