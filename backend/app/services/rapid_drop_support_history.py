"""수동 지지 좌표를 최초 관찰 시각부터 별도 JSONL에 기록한다.

사용자 manual_lines.db를 열거나 수정하지 않는다. 호출자는 이미 읽은 BTCUSDT 1D
수동 도형 목록을 전달한다. 현재 좌표의 created_at으로 과거를 추측하지 않는다.
날짜 질의는 UTC 다음 날 00:00 직전까지 알려진 마지막 좌표를 해당 일봉에 쓴다.
기록은 API가 관찰한 시점만 증명한다. 두 관찰 사이에 발생했다가 되돌린 수정이나
다른 앱의 직접 DB 수정 시각을 복원할 수 없으므로 완전한 편집 이력으로 주장하지 않는다.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
from typing import Iterator

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "data" / "rapid_drop_support_versions.jsonl"
ENV_PATH = "CCX_RAPID_DROP_SUPPORT_HISTORY"
SCHEMA_VERSION = 1


class SupportHistoryError(ValueError):
    """불완전하거나 잠긴 기록은 지지 근거로 사용하지 않는다."""


def _path(path: str | Path | None) -> Path:
    return Path(path) if path is not None else Path(os.environ.get(ENV_PATH, DEFAULT_PATH))


def _utc(value: datetime | str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
        if not isinstance(parsed, datetime) or parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("UTC 시각에 시간대가 필요함")
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError) as exc:
        raise SupportHistoryError("지지 이력의 UTC 시각을 확인하세요.") from exc


def _stamp(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _hash(value: object) -> str:
    return sha256(_canonical(value)).hexdigest()


def _price(value: object) -> float:
    if isinstance(value, bool):
        raise SupportHistoryError("수동 지지 가격은 유한한 양수여야 합니다.")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise SupportHistoryError("수동 지지 가격은 유한한 양수여야 합니다.") from exc
    if not math.isfinite(result) or result <= 0:
        raise SupportHistoryError("수동 지지 가격은 유한한 양수여야 합니다.")
    return result


def _normalize(lines: list[dict]) -> dict:
    if not isinstance(lines, list):
        raise SupportHistoryError("도형 목록은 배열이어야 합니다.")
    state = []
    unsupported = []
    seen = set()
    for row in lines:
        if not isinstance(row, dict):
            raise SupportHistoryError("도형 행은 객체여야 합니다.")
        interval = row.get("interval", "1d")
        if not isinstance(interval, str):
            raise SupportHistoryError("수동 도형의 봉 간격을 확인하세요.")
        if row.get("symbol", "BTCUSDT") != "BTCUSDT" or interval.lower() != "1d":
            continue
        line_id = row.get("id")
        if isinstance(line_id, bool) or not isinstance(line_id, (int, str)) or not str(line_id):
            raise SupportHistoryError("수동 도형 ID를 확인하세요.")
        identity = str(line_id)
        if identity in seen:
            raise SupportHistoryError("같은 수동 도형 ID를 중복 입력할 수 없습니다.")
        seen.add(identity)
        kind = row.get("line_type")
        if kind not in ("horizontal", "zone"):
            unsupported.append(identity)
            continue
        bottom = top = _price(row.get("price1"))
        start = end = None
        if kind == "zone":
            other = _price(row.get("price2"))
            bottom, top = sorted((bottom, other))
            try:
                first, last = sorted((date.fromisoformat(row["time1"]), date.fromisoformat(row["time2"])))
            except (KeyError, ValueError, TypeError) as exc:
                raise SupportHistoryError("수동 존의 시작·종료 날짜를 확인하세요.") from exc
            if bottom == top or first == last:
                raise SupportHistoryError("수동 존의 가격·시간 범위는 0보다 커야 합니다.")
            start, end = first.isoformat(), last.isoformat()
        state.append(dict(id=identity, kind=kind, bottom=bottom, top=top, start=start, end=end))
    return dict(lines=sorted(state, key=lambda item: item["id"]), unsupported_line_ids=sorted(unsupported))


@contextmanager
def _locked(path: Path, *, create_parent: bool) -> Iterator[None]:
    try:
        if create_parent:
            path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SupportHistoryError("지지 버전 기록 디렉터리를 준비할 수 없습니다.") from exc
    lock = path.with_name(path.name + ".lock")
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise SupportHistoryError("지지 버전 기록이 잠겨 있습니다. 잠금을 확인하기 전에는 사용하지 않습니다.") from exc
    except OSError as exc:
        raise SupportHistoryError("지지 버전 기록 잠금을 만들 수 없습니다.") from exc
    try:
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        yield
    finally:
        os.close(descriptor)
        lock.unlink(missing_ok=True)


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        raw = path.read_bytes()
        if not raw or not raw.endswith(b"\n"):
            raise SupportHistoryError("지지 버전 기록이 불완전합니다. 원본을 보존하고 사용을 중단합니다.")
        records = []
        previous_hash = None
        previous_time = None
        for line in raw.decode("utf-8").splitlines():
            item = json.loads(line)
            if not isinstance(item, dict) or set(item) != {
                    "schema_version", "observed_at", "state", "fingerprint", "previous_hash", "record_hash"}:
                raise ValueError("잘못된 기록 형식")
            if item["schema_version"] != SCHEMA_VERSION:
                raise ValueError("지원하지 않는 기록 버전")
            observed = _utc(item["observed_at"])
            state = item["state"]
            if not isinstance(state, dict) or set(state) != {"lines", "unsupported_line_ids"}:
                raise ValueError("잘못된 좌표 상태")
            # 저장된 내부 좌표 역시 검증해 손상·임의 편집을 fail-closed 처리한다.
            reconstructed = []
            for row in state["lines"]:
                if set(row) != {"id", "kind", "bottom", "top", "start", "end"}:
                    raise ValueError("잘못된 좌표 행")
                reconstructed.append(dict(id=row["id"], line_type=row["kind"], price1=row["top"],
                    price2=row["bottom"], time1=row["start"], time2=row["end"]))
            unsupported = state["unsupported_line_ids"]
            if not isinstance(unsupported, list) or any(not isinstance(x, str) or not x for x in unsupported):
                raise ValueError("잘못된 미지원 도형 ID")
            normalized = _normalize(reconstructed)
            if normalized["lines"] != state["lines"] or sorted(set(unsupported)) != unsupported:
                raise ValueError("정규화되지 않은 좌표")
            if item["fingerprint"] != _hash(state) or item["previous_hash"] != previous_hash:
                raise ValueError("기록 연결 불일치")
            body = {key: value for key, value in item.items() if key != "record_hash"}
            if item["record_hash"] != _hash(body):
                raise ValueError("기록 해시 불일치")
            if previous_time is not None and observed <= previous_time:
                raise ValueError("기록 시각 역순·중복")
            records.append(item)
            previous_hash, previous_time = item["record_hash"], observed
        return records
    except SupportHistoryError:
        raise
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise SupportHistoryError("지지 버전 기록을 검증할 수 없습니다. 기존 파일을 보존하고 사용을 중단합니다.") from exc


def record_snapshot(lines: list[dict], observed_at: datetime | str | None = None,
                    path: str | Path | None = None) -> dict:
    """지금 관찰한 전체 도형 상태를 append한다. 동일한 상태의 반복 요청은 쓰지 않는다."""
    target = _path(path)
    observed = _utc(observed_at if observed_at is not None else datetime.now(timezone.utc))
    state = _normalize(lines)
    fingerprint = _hash(state)
    with _locked(target, create_parent=True):
        records = _read(target)
        if records and observed < _utc(records[-1]["observed_at"]):
            raise SupportHistoryError("과거 시각으로 지지 버전을 소급 기록할 수 없습니다.")
        if records and fingerprint == records[-1]["fingerprint"]:
            return dict(recorded=False, recording_started_at=records[0]["observed_at"],
                        last_observed_at=records[-1]["observed_at"], unsupported_line_ids=state["unsupported_line_ids"])
        if records and observed == _utc(records[-1]["observed_at"]):
            raise SupportHistoryError("같은 시각의 서로 다른 좌표 상태를 기록할 수 없습니다.")
        body = dict(schema_version=SCHEMA_VERSION, observed_at=_stamp(observed), state=state,
                    fingerprint=fingerprint, previous_hash=records[-1]["record_hash"] if records else None)
        record = dict(body, record_hash=_hash(body))
        try:
            with target.open("ab") as stream:
                stream.write(_canonical(record) + b"\n")
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as exc:
            raise SupportHistoryError("지지 버전 기록을 추가하지 못했습니다. 파일을 덮어쓰지 않습니다.") from exc
    return dict(recorded=True, recording_started_at=records[0]["observed_at"] if records else record["observed_at"],
                last_observed_at=record["observed_at"], unsupported_line_ids=state["unsupported_line_ids"])


def _query_bounds(as_of: date | datetime | str | None) -> tuple[datetime, date]:
    if as_of is None:
        as_of = datetime.now(timezone.utc)
    if isinstance(as_of, str):
        try:
            as_of = date.fromisoformat(as_of)
        except ValueError:
            as_of = _utc(as_of)
    try:
        if isinstance(as_of, datetime):
            point = _utc(as_of)
            return point + timedelta(microseconds=1), point.date() - timedelta(days=1)
        if isinstance(as_of, date):
            return datetime.combine(as_of + timedelta(days=1), time.min, timezone.utc), as_of
    except (ValueError, OverflowError) as exc:
        raise SupportHistoryError("조회 날짜 범위를 확인하세요.") from exc
    raise SupportHistoryError("조회 시각은 UTC 시각 또는 ISO 날짜여야 합니다.")


def load_levels(as_of: date | datetime | str | None = None, path: str | Path | None = None) -> dict:
    """당시 알려진 버전의 일봉용 Level 입력과 상태 메타데이터를 반환한다."""
    target = _path(path)
    cutoff, last_day = _query_bounds(as_of)
    if target.exists():
        with _locked(target, create_parent=False):
            all_records = _read(target)
    else:
        all_records = []
    records = [item for item in all_records if _utc(item["observed_at"]) < cutoff]
    warnings = ["기록 시작 이전의 도형 좌표·사용 가능 시점은 확인하지 못했습니다."]
    if not records:
        return dict(levels=[], status="unconfirmed", recording_started_at=None, last_observed_at=None,
                    unsupported_line_ids=[], warnings=warnings)
    opened: dict[str, dict] = {}
    versions = []
    for item in records:
        first_day = _utc(item["observed_at"]).date()
        current = {row["id"]: row for row in item["state"]["lines"]}
        for identity in list(opened):
            if identity not in current or opened[identity]["row"] != current[identity]:
                old = opened.pop(identity)
                versions.append(dict(old, through=first_day-timedelta(days=1)))
        for identity, row in current.items():
            if identity not in opened:
                version_hash = _hash(dict(row=row, observed_at=item["observed_at"]))[:20]
                opened[identity] = dict(row=row, known_from=first_day,
                    key=f"manual:{identity}:v{version_hash}", support_id=f"manual:{identity}")
    versions.extend(dict(value, through=last_day) for value in opened.values())
    levels = []
    for version in versions:
        row = version["row"]
        first = max(version["known_from"], date.fromisoformat(row["start"])) if row["start"] else version["known_from"]
        last = min(version["through"], last_day)
        if row["end"]:
            last = min(last, date.fromisoformat(row["end"]))
        if first <= last:
            levels.append(dict(key=version["key"], support_id=version["support_id"], bottom=row["bottom"],
                               top=row["top"], known_from=first.isoformat(), through=last.isoformat()))
    unsupported = records[-1]["state"]["unsupported_line_ids"]
    if unsupported:
        warnings.append("추세선·미지원 도형은 급락 지지 판정에서 제외했습니다.")
    return dict(levels=sorted(levels, key=lambda item: (item["known_from"], item["key"])), status="recorded",
                recording_started_at=records[0]["observed_at"], last_observed_at=records[-1]["observed_at"],
                unsupported_line_ids=unsupported, warnings=warnings)
