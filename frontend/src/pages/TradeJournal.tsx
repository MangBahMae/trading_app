import { useEffect, useState } from "react";
import TradeCloseForm from "../components/trade/TradeCloseForm";
import TradeDetail from "../components/trade/TradeDetail";
import TradeList from "../components/trade/TradeList";
import TradePlanForm from "../components/trade/TradePlanForm";
import { deleteTrade, getSignalTags, listTrades } from "../api/trades";
import type { Trade, TradeStatus } from "../types";
import styles from "./TradeJournal.module.css";

type View = "list" | "new-plan" | "detail" | "close";

interface Props {
  onOpenCalculator: () => void;
}

// 기능 2 (Phase 2-1) 최상위 페이지. 레코드 하나가 draft->open->closed로
// 이동하는 라이프사이클이라(기획서 0번), 화면도 목록/작성/상세/청산기록
// 네 뷰를 하나의 상태 안에서 전환하는 구조로 만들었다.
export default function TradeJournal({ onOpenCalculator }: Props) {
  const [view, setView] = useState<View>("list");
  const [trades, setTrades] = useState<Trade[]>([]);
  const [signalTags, setSignalTags] = useState<string[]>([]);
  const [statusFilter, setStatusFilter] = useState<TradeStatus | "all">("all");
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const reload = () => {
    listTrades(statusFilter === "all" ? undefined : statusFilter).then(setTrades);
  };

  useEffect(() => {
    getSignalTags().then(setSignalTags);
  }, []);

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter]);

  const selectedTrade = trades.find((t) => t.id === selectedId) ?? null;

  const handleSelect = (id: number) => {
    setSelectedId(id);
    setView("detail");
  };

  const handleSaved = () => {
    reload();
    setView("list");
  };

  const handleDelete = async () => {
    if (selectedId === null) return;
    if (!window.confirm("이 매매 기록을 삭제할까요? 되돌릴 수 없습니다.")) return;
    await deleteTrade(selectedId);
    reload();
    setView("list");
  };

  return (
    <div className={styles.page}>
      <h1>매매 기록</h1>

      {view === "list" && (
        <TradeList
          trades={trades}
          statusFilter={statusFilter}
          onFilterChange={setStatusFilter}
          onSelect={handleSelect}
          onNew={() => setView("new-plan")}
        />
      )}

      {view === "new-plan" && (
        <TradePlanForm
          signalTags={signalTags}
          onSaved={handleSaved}
          onCancel={() => setView("list")}
          onOpenCalculator={onOpenCalculator}
        />
      )}

      {view === "detail" && selectedTrade && (
        <TradeDetail
          trade={selectedTrade}
          onBack={() => setView("list")}
          onClose={() => setView("close")}
          onDelete={handleDelete}
        />
      )}

      {view === "close" && selectedTrade && (
        <TradeCloseForm
          trade={selectedTrade}
          onSaved={(updated) => {
            setTrades((prev) => prev.map((t) => (t.id === updated.id ? updated : t)));
            setView("detail");
          }}
          onCancel={() => setView("detail")}
        />
      )}
    </div>
  );
}
