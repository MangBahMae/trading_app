// scripts/position_sizing.py의 format_krw_full / format_krw_compact /
// format_krw_with_compact / format_usdt_krw를 TS로 1:1 재구현.
//
// (이 로직은 이전 단계에서 Streamlit용 HTML/JS 위젯 안에 인라인으로 먼저
// 구현했던 것과 동일하며, Node로 직접 실행해 Python 쪽과 케이스 대조 검증을
// 거쳤다: 5,000,000 -> "500만원", 1,625,000 -> "162.5만원",
// 150,000,000 -> "1.5억원" 등.)

export function formatKrwFull(amount: number): string {
  return `${Math.round(amount).toLocaleString("en-US")}원`;
}

export function formatKrwCompact(amount: number): string {
  if (amount === 0) return "0원";
  const sign = amount < 0 ? "-" : "";
  const a = Math.abs(amount);

  if (a >= 100_000_000) {
    const eok = a / 100_000_000;
    const text = eok.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
    return `${sign}${text}억원`;
  }

  if (a >= 10_000) {
    const man = a / 10_000;
    let text: string;
    if (Math.abs(man - Math.round(man)) < 1e-9) {
      text = Math.round(man).toLocaleString("en-US");
    } else {
      text = man.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
    }
    return `${sign}${text}만원`;
  }

  return `${sign}${Math.round(a).toLocaleString("en-US")}원`;
}

export function formatKrwWithCompact(amount: number): string {
  return `${formatKrwFull(amount)} (${formatKrwCompact(amount)})`;
}

export function formatUsdtKrw(usdtAmount: number, exchangeRate: number): string {
  const krw = usdtAmount * exchangeRate;
  return `≈ ${formatKrwWithCompact(krw)}`;
}
