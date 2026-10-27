import type { ReactNode } from "react";
import styles from "./AppTopBar.module.css";

export type Menu = "scanner" | "position-sizing" | "trade-journal";

const MENU_ITEMS: { value: Menu; label: string }[] = [
  { value: "scanner", label: "신호 스캐너" },
  { value: "trade-journal", label: "매매 기록" },
  { value: "position-sizing", label: "포지션 사이징" },
];

// 화면 전환 메뉴 - 작은 텍스트 탭. 3개 화면이 공유한다(예전 App.tsx의 nav).
export function AppNav({ menu, onMenu }: { menu: Menu; onMenu: (menu: Menu) => void }) {
  return (
    <nav className={styles.nav} aria-label="화면 전환">
      {MENU_ITEMS.map((item) => (
        <button
          key={item.value}
          type="button"
          className={menu === item.value ? styles.navButtonActive : styles.navButton}
          onClick={() => onMenu(item.value)}
        >
          {item.label}
        </button>
      ))}
    </nav>
  );
}

interface Props {
  left?: ReactNode;     // 화면별 제목/보조 정보 (스캐너: "BTCUSDT · 1D" + 데이터 범위)
  nav: ReactNode;       // <AppNav />
  actions?: ReactNode;  // 화면별 오른쪽 동작 (스캐너: 새로고침 아이콘 버튼)
}

// 얇은 공용 상단 바: 왼쪽 정보 | 오른쪽 메뉴 탭 + 동작.
export default function AppTopBar({ left, nav, actions }: Props) {
  return (
    <header className={styles.bar}>
      <div className={styles.left}>{left}</div>
      <div className={styles.right}>
        {nav}
        {actions}
      </div>
    </header>
  );
}
