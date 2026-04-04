import type { ComputedRef, InjectionKey, Ref } from "vue";
import type { QuizBlockType } from "@/types/quiz-schema";

export type QuizFlowActions = {
  addBlock: (type: QuizBlockType) => void;
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
