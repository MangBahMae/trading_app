import { useState } from "react";
import PositionSizing from "./pages/PositionSizing";
import SignalScanner from "./pages/SignalScanner";
import styles from "./App.module.css";

type Menu = "scanner" | "position-sizing";

// Streamlit의 st.sidebar.radio("메뉴", ["신호 스캐너", "포지션 사이징"])에 대응.
function App() {
  const [menu, setMenu] = useState<Menu>("scanner");

  return (
    <div className={styles.app}>
      <nav className={styles.nav}>
        <button
          type="button"
          className={menu === "scanner" ? styles.navButtonActive : styles.navButton}
          onClick={() => setMenu("scanner")}
        >
          신호 스캐너
        </button>
        <button
          type="button"
          className={menu === "position-sizing" ? styles.navButtonActive : styles.navButton}
          onClick={() => setMenu("position-sizing")}
        >
          포지션 사이징
        </button>
      </nav>
      {menu === "scanner" ? <SignalScanner /> : <PositionSizing />}
    </div>
  );
}

export default App;
