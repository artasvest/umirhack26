import type { ComputedRef, InjectionKey, Ref } from "vue";
import type { QuizBlockType } from "@/types/quiz-schema";

/** MIME для drag-and-drop типа блока с палитры в конструктор */
export const QUIZ_PALETTE_DRAG_MIME = "application/x-quiz-block-type";

const ALLOWED_BLOCK_TYPES = new Set<QuizBlockType>(["single", "multi", "slider", "form", "ai_summary"]);

export function quizBlockTypeFromDragData(dt: DataTransfer): QuizBlockType | null {
  const v = dt.getData(QUIZ_PALETTE_DRAG_MIME) || dt.getData("text/plain");
  if (!v || !ALLOWED_BLOCK_TYPES.has(v as QuizBlockType)) return null;
  return v as QuizBlockType;
}

export type QuizFlowActions = {
  addBlock: (type: QuizBlockType, atFlowPosition?: { x: number; y: number }) => string;
  deleteSelection: () => void;
  /** Добавить вариант/пункт прямо на карточке (single/multi) */
  addCanvasOption: (nodeId: string) => void;
  setCanvasOptionLabel: (nodeId: string, optionId: string, label: string) => void;
};

/** После addCanvasOption — сфокусировать поле ввода этой опции на canvas */
export type CanvasOptionFocusRequest = { nodeId: string; optionId: string } | null;

export const quizFlowActionsKey: InjectionKey<QuizFlowActions> = Symbol("quizFlowActions");

export const quizCanvasOptionFocusKey: InjectionKey<Ref<CanvasOptionFocusRequest>> =
  Symbol("quizCanvasOptionFocus");

/** id блока → отображаемый заголовок для подписей и подсказок */
export const quizIdTitlesKey: InjectionKey<ComputedRef<Record<string, string>>> = Symbol("quizIdTitles");
