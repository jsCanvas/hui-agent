import type { VRM, VRMExpressionManager } from "@pixiv/three-vrm";
import type { AvatarMode } from "./types";

const EXPRESSION_CANDIDATES = {
  happy: ["happy", "Joy", "Smile"],
  relaxed: ["relaxed", "Neutral"],
  surprised: ["Surprised", "surprised"],
  sad: ["sad", "Sorrow"],
  angry: ["angry", "Angry"],
  aa: ["aa", "A", "Ah"],
  ih: ["ih", "I"],
  ou: ["ou", "O", "U"],
  ee: ["ee", "E"],
  oh: ["oh", "Oh"],
  blink: ["blink", "Blink"],
} as const;

type ExpressionKey = keyof typeof EXPRESSION_CANDIDATES;

function resolveExpressionName(em: VRMExpressionManager, key: ExpressionKey): string | null {
  const map = em.expressions.map((e) => e.expressionName);
  for (const candidate of EXPRESSION_CANDIDATES[key]) {
    if (map.includes(candidate)) return candidate;
  }
  return null;
}

function setExpr(em: VRMExpressionManager, key: ExpressionKey, value: number) {
  const name = resolveExpressionName(em, key);
  if (name) em.setValue(name, Math.max(0, Math.min(1, value)));
}

function resetExpressions(em: VRMExpressionManager) {
  for (const expr of em.expressions) {
    em.setValue(expr.expressionName, 0);
  }
}

export function applyVrmDialogue(
  vrm: VRM,
  mode: AvatarMode,
  mouthOpen: number,
  timeSec: number,
): void {
  const em = vrm.expressionManager;
  if (!em) return;

  resetExpressions(em);

  const blinkCycle = 4.5;
  const blinkPhase = timeSec % blinkCycle;
  const blink =
    blinkPhase < 0.12
      ? Math.sin((blinkPhase / 0.12) * Math.PI)
      : blinkPhase > blinkCycle - 0.08
        ? Math.sin(((blinkCycle - blinkPhase) / 0.08) * Math.PI) * 0.25
        : 0;
  setExpr(em, "blink", blink);

  const mouth = Math.max(0, Math.min(1, mouthOpen));

  switch (mode) {
    case "speaking":
      setExpr(em, "aa", mouth * 0.95);
      setExpr(em, "oh", mouth * 0.35);
      setExpr(em, "ee", mouth * 0.2);
      setExpr(em, "relaxed", 0.15);
      break;
    case "listening":
      setExpr(em, "happy", 0.25);
      setExpr(em, "surprised", 0.12);
      setExpr(em, "aa", 0.05);
      break;
    case "waiting":
    case "executing":
      setExpr(em, "sad", 0.08);
      setExpr(em, "surprised", 0.18);
      break;
    case "completed":
      setExpr(em, "happy", 0.85);
      setExpr(em, "aa", 0.08);
      break;
    case "conversation":
      setExpr(em, "happy", 0.35);
      setExpr(em, "relaxed", 0.2);
      break;
    default:
      setExpr(em, "relaxed", 0.45);
      setExpr(em, "happy", 0.12);
      break;
  }

  em.update();
}

export function applyVrmIdleMotion(vrm: VRM, timeSec: number, mode: AvatarMode): void {
  const head = vrm.humanoid?.getNormalizedBoneNode("head");
  const neck = vrm.humanoid?.getNormalizedBoneNode("neck");
  if (!head) return;

  const sway = Math.sin(timeSec * 1.4) * 0.04;
  const nod = Math.sin(timeSec * 2.1) * 0.02;
  head.rotation.y = sway + (mode === "listening" ? 0.06 : 0);
  head.rotation.x = nod + (mode === "executing" || mode === "waiting" ? -0.05 : 0);
  if (neck) neck.rotation.y = sway * 0.4;
}
