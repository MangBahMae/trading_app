import type {
  ISeriesApi, ISeriesPrimitive, ISeriesPrimitivePaneRenderer, ISeriesPrimitivePaneView,
  SeriesAttachedParameter, SeriesType, Time,
} from "lightweight-charts";
import { trendHandlePoints, trendSegmentPixels, type TrendSpec } from "./chartLogic";
import type { TimeAxis } from "./timeAxis";

export interface TrendLineSpec extends TrendSpec {
  selected: boolean; // 클릭으로 선택됨 - 굵은 실선 + 양 끝점 핸들로 강조
}

type DrawTarget = Parameters<ISeriesPrimitivePaneRenderer["draw"]>[0];

const HANDLE_SIZE_PX = 8;

// 추세선: 두 점 사이 선분만 그린다(양쪽 연장 없음 - 백엔드 신호도 같은 구간만 평가). 라인 시리즈는
// 미래 시간에 점을 넣으면 시간축에 "한 칸"만 생겨서 마지막 캔들 오른쪽 빈 공간의 위치가 틀어지므로,
// 존처럼 프리미티브로 그려서 시간 -> x를 timeAxis(논리 인덱스 기반)로 직접 계산한다. 두 점이 같은 날이면
// price1 높이의 수평 선분이다. 기존 모양(#c62828, 1px 점선 / 선택 시 #b71c1c, 3px 실선)을 그대로 따르고,
// 선택되면 양 끝점에 작은 정사각형 핸들을 그린다. 끝점 드래그 중에는 setOverride()로 임시 모양을 넣어
// 실시간으로 보여준다(저장 전).
export class TrendLinePrimitive implements ISeriesPrimitive<Time> {
  private series: ISeriesApi<SeriesType> | null = null;
  private requestUpdate: (() => void) | null = null;
  private readonly view: ISeriesPrimitivePaneView;
  private readonly spec: TrendLineSpec;
  private readonly axis: TimeAxis;
  private override: TrendSpec | null = null;

  constructor(spec: TrendLineSpec, axis: TimeAxis) {
    this.spec = spec;
    this.axis = axis;
    this.view = {
      zOrder: () => "normal",
      renderer: () => ({ draw: (target: DrawTarget) => this.draw(target) }),
    };
  }

  attached(param: SeriesAttachedParameter<Time>): void {
    this.series = param.series;
    this.requestUpdate = param.requestUpdate;
  }

  detached(): void {
    this.series = null;
    this.requestUpdate = null;
  }

  paneViews(): readonly ISeriesPrimitivePaneView[] {
    return [this.view];
  }

  // 드래그 중 임시 모양(null이면 원래 모양). 서버에 저장하기 전의 미리보기다.
  setOverride(geom: TrendSpec | null): void {
    this.override = geom;
    this.requestUpdate?.();
  }

  private draw(target: DrawTarget): void {
    const { series, axis } = this;
    if (!series) return;
    const spec: TrendLineSpec = this.override ? { ...this.spec, ...this.override } : this.spec;

    target.useMediaCoordinateSpace(({ context }) => {
      const priceToY = (p: number) => series.priceToCoordinate(p);
      const seg = trendSegmentPixels(spec, axis.dateToX, priceToY);
      if (!seg) return;

      context.strokeStyle = spec.selected ? "#b71c1c" : "#c62828";
      context.lineWidth = spec.selected ? 3 : 1;
      context.setLineDash(spec.selected ? [] : [6, 4]);
      context.beginPath();
      context.moveTo(seg.x1, seg.y1);
      context.lineTo(seg.x2, seg.y2);
      context.stroke();
      context.setLineDash([]);

      if (spec.selected) {
        const pts = trendHandlePoints(spec, axis.dateToX, priceToY);
        if (!pts) return;
        const half = HANDLE_SIZE_PX / 2;
        context.fillStyle = "#ffffff";
        context.strokeStyle = "#1565c0";
        context.lineWidth = 1.5;
        for (const p of [pts.p1, pts.p2]) {
          context.fillRect(p.x - half, p.y - half, HANDLE_SIZE_PX, HANDLE_SIZE_PX);
          context.strokeRect(p.x - half, p.y - half, HANDLE_SIZE_PX, HANDLE_SIZE_PX);
        }
      }
    });
  }
}
