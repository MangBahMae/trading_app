import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// 기존 기본값은 유지하되 격리 검증 서버의 포트만 선택한다. 외부 호스트는 받지 않는다.
const apiPortValue = process.env.CCX_TEST_API_PORT ?? "8000";
if (!/^\d{1,5}$/.test(apiPortValue) || Number(apiPortValue) < 1 || Number(apiPortValue) > 65535) {
  throw new Error("CCX_TEST_API_PORT는 1~65535 범위의 로컬 포트여야 합니다.");
}
const testApiBaseUrl = `http://localhost:${Number(apiPortValue)}`;

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
    // 여러 테스트 파일이 전부 같은 실제 백엔드(+ trades.db 등 공유 상태)에
    // 붙어서 통합 테스트를 하기 때문에(브라우저 자동화 도구가 없어서 택한
    // 방식), 파일들을 병렬로 돌리면 동시 요청 부하로 일부 테스트가 기본
    // 타임아웃(5000ms)을 넘겨 flaky해진다 - 파일 단위는 직렬로 돌린다.
    fileParallelism: false,
    testTimeout: 15000,
    // 테스트(jsdom)에는 Vite 개발 서버 프록시가 없어서 상대 경로 fetch가 안 된다 - 실제로 떠 있는
    // 백엔드 주소를 직접 알려준다.
    env: { VITE_API_BASE_URL: testApiBaseUrl },
  },
});
