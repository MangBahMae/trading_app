import type { ReactNode } from "react";
import type { DrawMode } from "../types";
import styles from "./ToolRail.module.css";

const SVG_PROPS = {
  width: 20, height: 20, viewBox: "0 0 20 20", fill: "none", stroke: "currentColor", strokeWidth: 1.6,
  strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true,
} as const;

const ICONS: Record<DrawMode, ReactNode> = {
  select: (
    <svg {...SVG_PROPS}><path d="M5 3.5l10 6.2-4.4 1.2-1.4 4.4z" fill="currentColor" fillOpacity={0.25} /></svg>
  ),
  horizontal: (
    <svg {...SVG_PROPS}><line x1="3" y1="10" x2="17" y2="10" /><circle cx="10" cy="10" r="1.6" fill="currentColor" /></svg>
  ),
  trend: (
    <svg {...SVG_PROPS}>
      <line x1="4.5" y1="15.5" x2="15.5" y2="4.5" />
      <circle cx="4.5" cy="15.5" r="1.7" fill="currentColor" /><circle cx="15.5" cy="4.5" r="1.7" fill="currentColor" />
    </svg>
  ),
  zone: (
    <svg {...SVG_PROPS}><rect x="3.5" y="5.5" width="13" height="9" rx="1" fill="currentColor" fillOpacity={0.2} /></svg>
  ),
};

// label은 접근성 이름(기존 라디오 라벨 그대로), tip은 hover 툴팁 문구.
export const DRAW_TOOLS: { value: DrawMode; label: string; tip: string }[] = [
  { value: "select", label: "캔들 선택", tip: "캔들 선택" },
  { value: "horizontal", label: "수평선 그리기 (클릭 1번)", tip: "수평선 · 클릭 1번" },
  { value: "trend", label: "추세선 그리기 (클릭 2번)", tip: "추세선 · 클릭 2번" },
  { value: "zone", label: "존 그리기 (클릭 2번)", tip: "존 · 클릭 2번" },
];

interface Props {
  mode: DrawMode;
  onChange: (mode: DrawMode) => void;
  // false면 그리기 도구(선택 제외)를 비활성화한다 - 1W에서는 일봉 선/존을 표시만 하고 그리지 못한다.
  drawingEnabled?: boolean;
}

// 왼쪽 세로 도구 막대 - 그리기 모드를 아이콘 버튼으로 고른다(예전 라디오 대체). 하나만 활성.
export default function ToolRail({ mode, onChange, drawingEnabled = true }: Props) {
  return (
    <div className={styles.rail} role="radiogroup" aria-label="그리기 도구">
      {DRAW_TOOLS.map((tool) => {
        const disabled = !drawingEnabled && tool.value !== "select";
        return (
          <button
            key={tool.value}
            type="button"
            role="radio"
            aria-checked={mode === tool.value}
            aria-label={tool.label}
            data-tip={disabled ? `${tool.tip.split(" · ")[0]} · 1D에서만 그릴 수 있음` : tool.tip}
            disabled={disabled}
            className={mode === tool.value ? styles.toolActive : styles.tool}
            onClick={() => onChange(tool.value)}
          >
            {ICONS[tool.value]}
          </button>
        );
      })}
    </div>
  );
}
