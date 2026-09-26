import "@testing-library/jest-dom/vitest";

// jsdom엔 window.matchMedia가 없음(잘 알려진 gap) - lightweight-charts가 내부적으로
// devicePixelRatio 관찰에 이걸 쓰므로, 표준 폴리필을 넣어준다.
if (typeof window !== "undefined" && !window.matchMedia) {
  window.matchMedia = (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }) as unknown as MediaQueryList;
}
