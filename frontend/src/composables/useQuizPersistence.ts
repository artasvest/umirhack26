import { watch, type Ref } from "vue";
import type { QuizBlockType } from "@/types/quiz-schema";

const STORAGE_KEY = "studio_quiz_schema_v1";

export interface QuizFormState {
  name: string;
  phoneDigits: string;
  email: string;
  comment: string;
  consent: boolean;
}

export interface QuizStepEntry {
  nodeId: string;
  title: string;
  value: string | number | string[];
  /** Тип блока схемы — бэкенд строит резюме даже без step1..step5 в id */
  blockType?: QuizBlockType;
}

export interface PersistedSchemaQuiz {
  fingerprint: string;
  navStack: string[];
  steps: QuizStepEntry[];
  answersByNode: Record<string, unknown>;
  form: QuizFormState;
  aiSummary: string;
}

function defaultForm(): QuizFormState {
  return {
    name: "",
    phoneDigits: "",
    email: "",
    comment: "",
    consent: false,
  };
}

export function loadPersisted(): PersistedSchemaQuiz | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const p = JSON.parse(raw) as PersistedSchemaQuiz;
    if (!p.form) p.form = defaultForm();
    if (!Array.isArray(p.navStack)) p.navStack = [];
    if (!Array.isArray(p.steps)) p.steps = [];
    if (!p.answersByNode || typeof p.answersByNode !== "object") p.answersByNode = {};
    return p;
  } catch {
    return null;
  }
}

export function savePersisted(state: PersistedSchemaQuiz): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

export function clearPersisted(): void {
  localStorage.removeItem(STORAGE_KEY);
}

export function watchPersistSchema(
  fingerprint: Ref<string>,
  navStack: Ref<string[]>,
  steps: Ref<QuizStepEntry[]>,
  answersByNode: Ref<Record<string, unknown>>,
  form: Ref<QuizFormState>,
  aiSummary: Ref<string>,
): void {
  watch(
    [fingerprint, navStack, steps, answersByNode, form, aiSummary],
    () => {
      if (!fingerprint.value) return;
      savePersisted({
        fingerprint: fingerprint.value,
        navStack: [...navStack.value],
        steps: [...steps.value],
        answersByNode: { ...answersByNode.value },
        form: { ...form.value },
        aiSummary: aiSummary.value,
      });
    },
    { deep: true },
  );
}
