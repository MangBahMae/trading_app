import { useEffect, useState } from "react";
import { calculatePosition, getExchangeRate } from "../api/client";
import NumberInput from "../components/NumberInput";
import PriceWeightList from "../components/PriceWeightList";
import type { CalculateResponse, Direction, PriceWeightItem } from "../types";
import { formatKrwWithCompact, formatUsdtKrw } from "../utils/krwFormat";
import styles from "./PositionSizing.module.css";

const DEBOUNCE_MS = 200;
const FALLBACK_RATE = 1350.0;

export default function PositionSizing() {
  // --- 환율 ---
  const [exchangeRate, setExchangeRate] = useState<number>(FALLBACK_RATE);
  const [rateSource, setRateSource] = useState<"live" | "fallback" | "loading">("loading");

  const loadRate = (refresh: boolean) => {
    // 최초 마운트 시(refresh=false)는 useState 초깃값이 이미 "loading"이라
    // 여기서 다시 set할 필요가 없다 - 새로고침 버튼 클릭(refresh=true)일 때만
    // "loading"으로 되돌린다.
    if (refresh) {
      setRateSource("loading");
    }
    getExchangeRate(refresh)
      .then((res) => {
        setExchangeRate(res.rate);
        setRateSource(res.source);
      })
      .catch(() => setRateSource("fallback"));
  };

  useEffect(() => {
    loadRate(false);
  }, []);

  // --- 입력 상태 ---
  const [balanceUsdt, setBalanceUsdt] = useState(350);
  const [riskPct, setRiskPct] = useState(1.0);
  const [direction, setDirection] = useState<Direction>("long");
  const [entries, setEntries] = useState<PriceWeightItem[]>([{ price: 0, weight: 100 }]);
  const [stopLoss, setStopLoss] = useState(0);
  const [takeProfits, setTakeProfits] = useState<PriceWeightItem[]>([]);
  const [marginInput, setMarginInput] = useState(0);

  // 원화 환산은 어디까지나 화면 표시(참고용 캡션)에만 쓰고, 계산 API에는
  // balanceUsdt를 그대로 넘긴다 - 진입가/SL/TP가 전부 USDT로 입력되는데
  // 잔고만 원화로 바꿔서 보내면 "포지션 사이즈 = 원화 리스크금액 ÷ USDT 진입가"
  // 처럼 서로 다른 통화가 섞여 BTC 수량이 완전히 틀어지는 버그가 있었다
  // (예: 잔고 300 USDT인데 결과가 BTC 0.96개로 나오는 등) - 발견 후 수정.
  const balanceKrw = balanceUsdt * exchangeRate;

  // --- 계산 결과 (짧은 디바운스로 백엔드 호출 - calculate_position 로직 자체는
  // 백엔드에만 있고 프론트로 옮기지 않았으므로 매번 서버에 물어봐야 함) ---
  const [result, setResult] = useState<CalculateResponse | null>(null);
  const [calcError, setCalcError] = useState<string | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => {
      calculatePosition({
        balance: balanceUsdt,
        risk_pct: riskPct,
        direction,
        entries,
        stop_loss: stopLoss,
        take_profits: takeProfits,
        margin: marginInput > 0 ? marginInput : null,
      })
        .then((res) => {
          setResult(res);
          setCalcError(null);
        })
        .catch((err) => setCalcError(String(err)));
    }, DEBOUNCE_MS);

    return () => clearTimeout(timer);
  }, [balanceUsdt, riskPct, direction, entries, stopLoss, takeProfits, marginInput]);

  return (
    <div className={styles.page}>
      <h1>포지션 사이징 계산기</h1>

      <div className={styles.rateBar}>
        {rateSource === "loading" && <span>환율 조회 중...</span>}
        {rateSource === "live" && (
          <span>환율(자동, USD/KRW 기준): 1 USDT ≈ {exchangeRate.toLocaleString("en-US", { maximumFractionDigits: 2 })}원</span>
        )}
        {rateSource === "fallback" && (
          <span>환율 자동 조회 실패 - 기본값 사용 중: 1 USDT ≈ {exchangeRate.toLocaleString("en-US")}원</span>
        )}
        <button type="button" onClick={() => loadRate(true)}>
          환율 새로고침
        </button>
      </div>

      <div className={styles.columns}>
        {/* 좌측: 입력 */}
        <div className={styles.col}>
          <h2>입력</h2>

          <label className={styles.fieldLabel} htmlFor="balance-usdt">잔고 (USDT)</label>
          <NumberInput id="balance-usdt" min={0} step={10} value={balanceUsdt} onChange={setBalanceUsdt} />
          {balanceUsdt > 0 && (
            <div className={styles.caption}>확정값: {formatKrwWithCompact(balanceKrw)}</div>
          )}

          <label className={styles.fieldLabel} htmlFor="risk-pct">리스크 %</label>
          <NumberInput id="risk-pct" min={0} step={0.1} value={riskPct} onChange={setRiskPct} />

          <label className={styles.fieldLabel}>방향</label>
          <div className={styles.radioGroup}>
            <label htmlFor="direction-long">
              <input
                id="direction-long"
                type="radio"
                name="direction"
                checked={direction === "long"}
                onChange={() => setDirection("long")}
              />
              롱
            </label>
            <label htmlFor="direction-short">
              <input
                id="direction-short"
                type="radio"
                name="direction"
                checked={direction === "short"}
                onChange={() => setDirection("short")}
              />
              숏
            </label>
          </div>

          <h3>진입가</h3>
          <PriceWeightList
            label="진입"
            minItems={1}
            exchangeRate={exchangeRate}
            onChange={setEntries}
          />

          <label className={styles.fieldLabel} htmlFor="stop-loss">손절가</label>
          <NumberInput id="stop-loss" min={0} step={1} value={stopLoss} onChange={setStopLoss} />
          {stopLoss > 0 && exchangeRate > 0 && (
            <div className={styles.caption}>
              {stopLoss.toLocaleString("en-US")} USDT {formatUsdtKrw(stopLoss, exchangeRate)}
            </div>
          )}

          <h3>TP가</h3>
          <PriceWeightList
            label="TP"
            minItems={0}
            exchangeRate={exchangeRate}
            onChange={setTakeProfits}
          />

          <label className={styles.fieldLabel} htmlFor="margin-input">투입 마진 (USDT, 선택, 0이면 레버리지 생략)</label>
          <NumberInput id="margin-input" min={0} step={10} value={marginInput} onChange={setMarginInput} />
        </div>

        {/* 우측: 결과 */}
        <div className={styles.col}>
          <h2>결과</h2>

          {calcError && <div className={styles.errorBox}>{calcError}</div>}

          {result && (
            <>
              <div className={styles.metrics}>
                <div className={styles.metric}>
                  <div className={styles.metricLabel}>1R (리스크 금액)</div>
                  <div className={styles.metricValue}>{result.risk_amount.toLocaleString("en-US", { maximumFractionDigits: 2 })} USDT</div>
                  <div className={styles.caption}>{formatUsdtKrw(result.risk_amount, exchangeRate)}</div>
                </div>
                <div className={styles.metric}>
                  <div className={styles.metricLabel}>포지션 사이즈</div>
                  {result.position_size !== null ? (
                    <>
                      <div className={styles.metricValue}>
                        {result.position_size.toLocaleString("en-US", { maximumFractionDigits: 2 })} USDT
                      </div>
                      <div className={styles.caption}>{formatUsdtKrw(result.position_size, exchangeRate)}</div>
                    </>
                  ) : (
                    <div className={styles.metricValue}>계산 불가</div>
                  )}
                </div>
              </div>

              <p>예상 평단: {result.avg_entry.toLocaleString("en-US", { maximumFractionDigits: 2 })} USDT</p>
              <p>손절 폭: {(result.stop_pct * 100).toFixed(2)}%</p>
              {result.btc_quantity !== null ? (
                <p>BTC 수량: {result.btc_quantity.toFixed(6)}</p>
              ) : (
                <p>BTC 수량: 계산 불가 (손절가가 진입가와 동일)</p>
              )}
              {result.leverage !== null && <p>레버리지: {result.leverage.toFixed(2)}배</p>}

              {result.tp_results.length > 0 && (
                <>
                  <h3>TP별 R값</h3>
                  <table className={styles.tpTable}>
                    <thead>
                      <tr>
                        <th>가격</th>
                        <th>비중%</th>
                        <th>R배수</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.tp_results.map((tp, i) => (
                        <tr key={i}>
                          <td>{tp.price.toLocaleString("en-US")}</td>
                          <td>{tp.weight_pct}</td>
                          <td>{tp.r_multiple.toFixed(4)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {result.weighted_avg_r !== null && (
                    <>
                      <p>가중평균 R: {result.weighted_avg_r.toFixed(2)}</p>
                      <p>손익비: 1 : {result.weighted_avg_r.toFixed(2)}</p>
                    </>
                  )}
                </>
              )}

              {result.warning_messages.map((msg, i) => (
                <div key={i} className={styles.warningBox}>
                  {msg}
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
