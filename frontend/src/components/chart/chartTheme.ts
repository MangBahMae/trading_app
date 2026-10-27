// 차트 전용 다크 팔레트 - 색 리터럴을 한 곳에 모아 차트/프리미티브/오버레이가 같은 값을 쓴다.
// (CSS 쪽 색은 index.css의 변수를 쓴다. 값은 트레이딩뷰 다크 테마를 참고했다.)
export const THEME = {
  background: "#131722",
  text: "#d1d4dc",
  grid: "#2a2e39",
  border: "#363a45",
  crosshair: "#758696",

  up: "#26a69a",
  down: "#ef5350",
  // 선택한 캔들만 선명하게 보이고 나머지는 흐리게 보이는 하이라이트용 (다크 배경에서 "흐림" = 어두운 쪽으로)
  dimUp: "#2f8277",
  dimDown: "#a9504f",
  volDimUp: "rgba(38, 166, 154, 0.3)",
  volDimDown: "rgba(239, 83, 80, 0.3)",
  volVividUp: "rgba(38, 166, 154, 0.8)",
  volVividDown: "rgba(239, 83, 80, 0.8)",

  ema9: "#4da3ff",
  ema20: "#ff9800",
  ema50: "#b388ff",
  ema200: "#d1d4dc",
  rsi: "#ba68c8",
  rsi70: "#ff6f42",
  rsi30: "#5c8cff",

  horizontalLine: "#4a90ff",
  horizontalLineSelected: "#9ec1ff",
  trendLine: "#ff5252",
  trendLineSelected: "#ff8a80",
  handleFill: "#ffffff",
  handleStroke: "#2962ff",

  zone: {
    below: { fill: "rgba(38, 166, 154, 0.18)", border: "rgba(38, 166, 154, 0.85)" },
    above: { fill: "rgba(239, 83, 80, 0.18)", border: "rgba(239, 83, 80, 0.85)" },
    inside: { fill: "rgba(245, 190, 40, 0.22)", border: "rgba(214, 158, 0, 0.9)" },
  },
  marketState: { A: "rgba(160, 160, 160, 0.16)", BC: "rgba(66, 133, 244, 0.18)" },

  preview: {
    horizontal: "rgba(100, 160, 255, 0.7)",
    trend: "rgba(255, 82, 82, 0.7)",
    zoneFill: "rgba(66, 165, 245, 0.14)",
    zoneBorder: "rgba(66, 165, 245, 0.8)",
    firstPoint: "#ff9800",
    firstPointText: "#131722",
  },

  divergenceUp: "#26a69a",
  divergenceDown: "#ef5350",
  divergenceFallback: "#8a8f9c",
  divergenceConfirmed: "#ffffff",

  // 도형 삭제 툴바 / 드래그 에러 박스 (DOM 오버레이)
  overlayBg: "#1e222d",
  overlayBorder: "#434651",
  overlayText: "#d1d4dc",
  errorBg: "#3b1f22",
  errorText: "#ff8a80",
  errorBorder: "#7f2d33",
} as const;
