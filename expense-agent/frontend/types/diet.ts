export type MealType = "Breakfast" | "Lunch" | "Dinner" | "Snack";

export type Meal = {
  id: number;
  name: string;
  meal_type: MealType | string;
  calories: number;
  protein?: number | null;
  carbs?: number | null;
  fat?: number | null;
  fiber?: number | null;
  notes?: string | null;
  source: string;
  eaten_at: string;
  created_at: string;
};

export type MealEstimate = {
  name: string;
  calories: number;
  protein: number;
  carbs: number;
  fat: number;
  fiber: number;
  source?: "memory" | "branded" | "ai" | "heuristic";
};

export type DietDay = {
  date: string;
  calorie_goal: number;
  protein_goal: number;
  calories: number;
  remaining: number;
  protein: number;
  protein_remaining: number;
  carbs: number;
  fat: number;
  fiber: number;
  meals: Meal[];
};

export type DietMonth = {
  month: string;
  streak_days: number;
  grace_misses?: number;
  streak_broken?: boolean;
  streak_ended_length?: number | null;
  days: Array<{
    date: string;
    hit_goal: boolean;
  }>;
};
