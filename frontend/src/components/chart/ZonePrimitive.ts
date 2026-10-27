import type {
  IChartApi, ISeriesApi, ISeriesPrimitive, ISeriesPrimitivePaneRenderer, ISeriesPrimitivePaneView,
  SeriesAttachedParameter, SeriesType, Time,
} from "lightweight-charts";
import { ZONE_COLORS, zoneColorKind, zoneHorizontalSpan, type ZoneGeom } from "./chartLogic";
import type { TimeAxis } from "./timeAxis";

export interface ZoneSpec {
  time1: string;   // 시작 (YYYY-MM-DD)
  time2: string;   // 끝
  top: number;     // 구간 상단 가격
  bottom: number;  // 구간 하단 가격
  selected: boolean; // 클릭으로 선택됨 - 굵은 테두리 + 네 꼭지점 핸들로 강조
}

export interface ZoneContext {
  axis: TimeAxis;            // 날짜 -> x 변환(미래 날짜 포함)과 표시 중인 첫 캔들 날짜
  lastClose: number | null;  // 색 결정용 마지막 종가
}

type DrawTarget = Parameters<ISeriesPrimitivePaneRenderer["draw"]>[0];

const HANDLE_SIZE_PX = 8;

// lightweight-charts 4.1 시리즈 프리미티브로 그리는 존(반투명 직사각형).
// 좌표는 그릴 때마다(줌/스크롤/가격축 변화마다) 차트에서 다시 구하므로 가격/시간에
// 맞게 계속 따라온다. 선택된 존은 네 꼭지점에 작은 정사각형 핸들을 그린다.
// 꼭지점 드래그 중에는 setOverride()로 임시 모양을 넣어 실시간으로 보여준다(저장 전).
export class ZonePrimitive implements ISeriesPrimitive<Time> {
  private chart: IChartApi | null = null;
  private series: ISeriesApi<SeriesType> | null = null;
  private requestUpdate: (() => void) | null = null;
  private readonly view: ISeriesPrimitivePaneView;
  private readonly spec: ZoneSpec;
  private readonly ctx: ZoneContext;
  private override: ZoneGeom | null = null;

  constructor(spec: ZoneSpec, ctx: ZoneContext) {
    this.spec = spec;
    this.ctx = ctx;
    this.view = {
      zOrder: () => "bottom", // 캔들/선 아래에 깔아서 캔들이 가려지지 않게
      renderer: () => ({ draw: (target: DrawTarget) => this.draw(target) }),
    };
  }

  attached(param: SeriesAttachedParameter<Time>): void {
    this.chart = param.chart as IChartApi;
    this.series = param.series;
    this.requestUpdate = param.requestUpdate;
  }

  detached(): void {
    this.chart = null;
    this.series = null;
    this.requestUpdate = null;
  }

  paneViews(): readonly ISeriesPrimitivePaneView[] {
    return [this.view];
  }

  // 드래그 중 임시 모양(null이면 원래 모양). 서버에 저장하기 전의 미리보기다.
  setOverride(geom: ZoneGeom | null): void {
    this.override = geom;
    this.requestUpdate?.();
  }

  private draw(target: DrawTarget): void {
    const { chart, series, ctx } = this;
    if (!chart || !series) return;
    const spec: ZoneSpec = this.override
      ? {
        ...this.spec, time1: this.override.time1, time2: this.override.time2,
        top: this.override.price1, bottom: this.override.price2,
      }
      : this.spec;

    target.useMediaCoordinateSpace(({ context }) => {
      const yTop = series.priceToCoordinate(spec.top);
      const yBottom = series.priceToCoordinate(spec.bottom);
      if (yTop === null || yBottom === null) return;

      // 시작이 데이터 이전이면 왼쪽 끝에서 자르고, 끝이 미래면 계산한 좌표 그대로 그린다.
      const span = zoneHorizontalSpan(spec.time1, spec.time2, ctx.axis.firstDate, ctx.axis.dateToX);
      if (!span) return;

      const [x1, x2] = span;
      const y = Math.min(yTop, yBottom);
      const h = Math.abs(yBottom - yTop);
      const color = ZONE_COLORS[zoneColorKind(spec.top, spec.bottom, ctx.lastClose)];

      context.fillStyle = color.fill;
      context.fillRect(x1, y, x2 - x1, h);
      const bw = spec.selected ? 3 : 1;
      context.strokeStyle = color.border;
      context.lineWidth = bw;
      context.strokeRect(x1 + bw / 2, y + bw / 2, Math.max(x2 - x1 - bw, 0), Math.max(h - bw, 0));

      if (spec.selected) {
        // 네 꼭지점 핸들. 시작이 데이터 이전이라 왼쪽에서 잘려 실제 꼭지점이 안 보이는 쪽은 그리지 않는다
        // (미래 쪽 꼭지점은 계산한 좌표에 그대로 그린다).
        const leftClipped = ctx.axis.firstDate !== null && spec.time1 < ctx.axis.firstDate;
        const half = HANDLE_SIZE_PX / 2;
        context.fillStyle = "#ffffff";
        context.strokeStyle = "#1565c0";
        context.lineWidth = 1.5;
        const drawHandle = (cx: number, cy: number) => {
          context.fillRect(cx - half, cy - half, HANDLE_SIZE_PX, HANDLE_SIZE_PX);
          context.strokeRect(cx - half, cy - half, HANDLE_SIZE_PX, HANDLE_SIZE_PX);
        };
        if (!leftClipped) { drawHandle(x1, y); drawHandle(x1, y + h); }
        drawHandle(x2, y);
        drawHandle(x2, y + h);
      }
    });
  }
}
