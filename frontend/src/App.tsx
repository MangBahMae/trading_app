import { useState } from "react";
import AppTopBar, { AppNav } from "./components/AppTopBar";
import type { Menu } from "./components/AppTopBar";
import PositionSizing from "./pages/PositionSizing";
import SignalScanner from "./pages/SignalScanner";
import TradeJournal from "./pages/TradeJournal";
import styles from "./App.module.css";

// 신호 스캐너는 자기 상단 바(제목/데이터 범위/새로고침)를 직접 그리고, 나머지 화면은 메뉴만 있는 공용 상단 바 아래에 둔다.
function App() {
  const [menu, setMenu] = useState<Menu>("scanner");
  const nav = <AppNav menu={menu} onMenu={setMenu} />;

  return (
    <div className={styles.app}>
      {menu === "scanner" ? (
        <SignalScanner nav={nav} />
      ) : (
        <>
          <AppTopBar nav={nav} />
          <div className={styles.scroll}>
            {menu === "trade-journal" && <TradeJournal onOpenCalculator={() => setMenu("position-sizing")} />}
            {menu === "position-sizing" && <PositionSizing />}
          </div>
        </>
      )}
    </div>
  );
}

export default App;
