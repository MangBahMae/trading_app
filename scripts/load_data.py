"""
data/ 폴더의 바이낸스 BTCUSDT 1d klines zip 파일들을 모두 읽어
하나의 시간순 정렬된 DataFrame으로 합치고, parquet으로 저장한다.

바이낸스 klines 컬럼 (헤더 없음, 12컬럼):
open_time, open, high, low, close, volume, close_time,
quote_asset_volume, number_of_trades, taker_buy_base_asset_volume,
taker_buy_quote_asset_volume, ignore

주의: 2025년 이후 데이터는 open_time/close_time이 마이크로초(us) 단위로 기록됨
(예: 1735689600000000 = 2025-01-01 00:00:00 UTC, 16자리).
"""
import zipfile
import io
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d.parquet"

COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_asset_volume", "number_of_trades",
    "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore",
]


def load_all() -> pd.DataFrame:
    frames = []
    zip_paths = sorted(DATA_DIR.glob("BTCUSDT-1d-*.zip"))
    if not zip_paths:
        raise FileNotFoundError(f"{DATA_DIR}에서 zip 파일을 찾지 못했습니다.")

    for zp in zip_paths:
        with zipfile.ZipFile(zp) as zf:
            csv_names = [n for n in zf.namelist() if n.endswith(".csv")]
            if len(csv_names) != 1:
                raise ValueError(f"{zp.name} 안에 CSV가 {len(csv_names)}개 있음 (1개 기대)")
            with zf.open(csv_names[0]) as f:
                raw = f.read()
            df = pd.read_csv(io.BytesIO(raw), header=None, names=COLUMNS)
            frames.append(df)

    merged = pd.concat(frames, ignore_index=True)

    # 타임스탬프 단위 판별: 자리수가 16자리면 마이크로초, 13자리면 밀리초
    sample = int(merged["open_time"].iloc[0])
    unit = "us" if len(str(sample)) >= 16 else "ms"

    for col in ["open_time", "close_time"]:
        merged[col] = pd.to_datetime(merged[col], unit=unit, utc=True)

    numeric_cols = ["open", "high", "low", "close", "volume",
                     "quote_asset_volume", "taker_buy_base_asset_volume",
                     "taker_buy_quote_asset_volume"]
    for col in numeric_cols:
        merged[col] = merged[col].astype(float)

    merged = merged.sort_values("open_time").reset_index(drop=True)

    before = len(merged)
    merged = merged.drop_duplicates(subset="open_time", keep="first").reset_index(drop=True)
    dup_count = before - len(merged)

    # 하루(1d) 간격 연속성 체크
    expected = pd.date_range(merged["open_time"].iloc[0], merged["open_time"].iloc[-1], freq="1D", tz="UTC")
    missing = expected.difference(merged["open_time"])

    print(f"파일 개수: {len(zip_paths)}")
    print(f"병합 전 행 수: {before}, 중복 제거 후: {len(merged)} (중복 {dup_count}개 제거)")
    print(f"기간: {merged['open_time'].iloc[0]} ~ {merged['open_time'].iloc[-1]}")
    print(f"전체 캔들 개수: {len(merged)}")
    print(f"기대 캔들 개수(1일 간격 기준): {len(expected)}")
    if len(missing) > 0:
        print(f"누락된 날짜 {len(missing)}개:")
        for d in missing:
            print(f"  - {d.date()}")
    else:
        print("누락된 날짜 없음 (연속적인 일봉 데이터)")

    return merged


if __name__ == "__main__":
    df = load_all()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PATH, index=False)
    print(f"\n저장 완료: {OUT_PATH}")
    print(df.head(3))
    print(df.tail(3))
