export type QuizBlockType = "single" | "multi" | "slider" | "form" | "ai_summary";

export interface QuizOption {
  id: string;
  label: string;
  nextStep?: string;
  image?: string;
}

export interface QuizNode {
  id: string;
  type: QuizBlockType;
  /** Номер для полосы прогресса (1…N). Важен при ветках: прыжок на «9-й» экран → 9/N, а не глубина стека. */
  displayOrder?: number;
  title?: string;
  options?: QuizOption[];
  min?: number;
  max?: number;
  step?: number;
  default?: number;
  nextStep?: string;
  position?: { x: number; y: number };
}

export interface QuizSchema {
  version?: number;
  nodes: QuizNode[];
  edges: { from: string; to: string }[];
}

export const QUIZ_BLOCK_TYPES: { value: QuizBlockType; label: string }[] = [
  { value: "single", label: "Одиночный выбор" },
  { value: "multi", label: "Множественный выбор" },
  { value: "slider", label: "Ползунок" },
  { value: "form", label: "Форма" },
  { value: "ai_summary", label: "ИИ-резюме" },
];
