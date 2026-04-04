import type { Edge, Node } from "@vue-flow/core";
import type { QuizNode, QuizSchema } from "@/types/quiz-schema";

function clone<T>(x: T): T {
  return JSON.parse(JSON.stringify(x)) as T;
}

/** Позиция по умолчанию: слева направо (как шаги квиза), с переносом строки */
const FLOW_ORIGIN_X = 48;
const FLOW_ORIGIN_Y = 88;
const FLOW_STEP_X = 300;
const FLOW_PER_ROW = 8;
const FLOW_ROW_GAP_Y = 228;

export function defaultFlowPosition(index: number): { x: number; y: number } {
  const col = index % FLOW_PER_ROW;
  const row = Math.floor(index / FLOW_PER_ROW);
  return {
    x: FLOW_ORIGIN_X + col * FLOW_STEP_X,
    y: FLOW_ORIGIN_Y + row * FLOW_ROW_GAP_Y,
  };
}

function nodeTitle(n: QuizNode): string {
  return (n.title?.trim() || n.id).slice(0, 42);
}

/** Для каждого single с опциями всегда рёбра с sourceHandle opt-* — иначе ручки не совпадают с ребром без handle */
export function schemaToFlowElements(schema: QuizSchema): { nodes: Node[]; edges: Edge[] } {
  const list = schema.nodes || [];
  const titleById: Record<string, string> = {};
  for (const n of list) {
    titleById[n.id] = nodeTitle(n);
  }

  const singleWithOptions = new Set(
    list.filter((n) => n.type === "single" && (n.options?.length ?? 0) > 0).map((n) => n.id),
  );

  const nodes: Node[] = list.map((n, i) => ({
    id: n.id,
    type: "quizBlock",
    position: n.position
      ? { x: Math.round(n.position.x), y: Math.round(n.position.y) }
      : defaultFlowPosition(i),
    data: { quiz: clone(n) },
  }));

  const edges: Edge[] = [];
  const seen = new Set<string>();
  const edgeKey = (s: string, t: string, h?: string | null) => `${s}|${h ?? ""}|${t}`;

  for (const e of schema.edges || []) {
    if (singleWithOptions.has(e.from)) continue;
    const k = edgeKey(e.from, e.to, null);
    if (seen.has(k)) continue;
    seen.add(k);
    edges.push({
      id: `e-${e.from}-${e.to}`,
      source: e.from,
      target: e.to,
      label: titleById[e.to] || e.to,
      style: { stroke: "#c9a962", strokeWidth: 2 },
    });
  }

  for (const n of list) {
    if (n.type !== "single" || !n.options?.length) continue;
    const fallback = schema.edges?.find((ed) => ed.from === n.id)?.to;
    for (const opt of n.options) {
      const t = opt.nextStep || fallback;
      if (!t) continue;
      const k = edgeKey(n.id, t, `opt-${opt.id}`);
      if (seen.has(k)) continue;
      seen.add(k);
      const targetTitle = titleById[t] || t;
      edges.push({
        id: `e-${n.id}-opt-${opt.id}-${t}`,
        source: n.id,
        target: t,
        sourceHandle: `opt-${opt.id}`,
        label: targetTitle,
        style: { stroke: "#d4b87a", strokeWidth: 2 },
      });
    }
  }

  return { nodes, edges };
}

export function flowToSchema(nodes: Node[], edges: Edge[]): QuizSchema {
  const vueEdges = edges;

  const schemaNodes: QuizNode[] = nodes.map((n) => {
    const q = clone((n.data as { quiz: QuizNode }).quiz);
    q.id = n.id;
    q.position = {
      x: Math.round(n.position.x),
      y: Math.round(n.position.y),
    };
    return q;
  });

  for (const q of schemaNodes) {
    if (q.type === "single" && q.options?.length) {
      const main = vueEdges.find((ed) => ed.source === q.id && !ed.sourceHandle?.startsWith("opt-"));
      for (const opt of q.options) {
        const specific = vueEdges.find(
          (ed) => ed.source === q.id && ed.sourceHandle === `opt-${opt.id}`,
        );
        const next = specific?.target ?? main?.target;
        opt.nextStep = next || undefined;
      }
    } else {
      const main = vueEdges.find((ed) => ed.source === q.id && !ed.sourceHandle?.startsWith("opt-"));
      if (main) q.nextStep = main.target;
    }
  }

  const schemaEdges: { from: string; to: string }[] = [];
  const dedupe = new Set<string>();

  for (const e of vueEdges) {
    if (e.sourceHandle?.startsWith("opt-")) continue;
    const k = `${e.source}->${e.target}`;
    if (dedupe.has(k)) continue;
    dedupe.add(k);
    schemaEdges.push({ from: e.source, to: e.target });
  }

  for (const q of schemaNodes) {
    if (q.type !== "single" || !q.options?.length) continue;
    const targets = [...new Set(q.options.map((o) => o.nextStep).filter(Boolean) as string[])];
    if (targets.length !== 1) continue;
    const t = targets[0];
    const hasFrom = schemaEdges.some((e) => e.from === q.id);
    if (!hasFrom && t) {
      schemaEdges.push({ from: q.id, to: t });
    }
  }

  return {
    version: 1,
    nodes: schemaNodes,
    edges: schemaEdges,
  };
}
