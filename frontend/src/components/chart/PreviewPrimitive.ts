import type {
  ISeriesApi, ISeriesPrimitive, ISeriesPrimitivePaneRenderer, ISeriesPrimitivePaneView,
  SeriesAttachedParameter, SeriesType, Time,
} from "lightweight-charts";
import type { DrawMode } from "../../types";
import type { TimeAxis } from "./timeAxis";

type DrawTarget = Parameters<ISeriesPrimitivePaneRenderer["draw"]>[0];

export interface PreviewPoint {
  time: string;
  price: number;
}

// 그리는 중인 도형의 미리보기("고무줄") - 첫 점(날짜/가격)과 마우스 위치(차트 컨테이너 기준
// 화면 좌표)로 그린다. 확정된 도형과 구분되게 점선 + 연한 색을 쓴다. 첫 점은 주황 점("1")으로
// 직접 그린다(캔들 시리즈 마커는 캔들이 없는 미래 날짜에 못 붙인다). 도형마다 시리즈를 만들었다
// 지웠다 하지 않고 프리미티브 하나의 상태만 바꾸므로, 확정/취소/모드 전환 때는 clear() 한 번이면
// 잔상이 안 남는다(차트가 지워지면 프리미티브도 같이 사라진다).
export class PreviewPrimitive implements ISeriesPrimitive<Time> {
  private series: ISeriesApi<SeriesType> | null = null;
  private requestUpdate: (() => void) | null = null;
  private readonly view: ISeriesPrimitivePaneView;

  private axis: TimeAxis | null = null;
  private mode: DrawMode = "select";
  private first: PreviewPoint | null = null;
  private mouse: { x: number; y: number } | null = null;

  constructor() {
    this.view = {
      zOrder: () => "top",
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

  // 표시 중인 캔들이 바뀔 때마다 갱신한다(날짜 -> x 변환에 쓴다).
  setAxis(axis: TimeAxis): void {
    this.axis = axis;
    this.requestUpdate?.();
  }

  setState(mode: DrawMode, first: PreviewPoint | null): void {
    this.mode = mode;
    this.first = first;
    this.requestUpdate?.();
  }

  setMouse(mouse: { x: number; y: number } | null): void {
    this.mouse = mouse;
    if (this.mode !== "select") this.requestUpdate?.();
  }

  clear(): void {
    this.mode = "select";
    this.first = null;
    this.mouse = null;
    this.requestUpdate?.();
  }

  private draw(target: DrawTarget): void {
    const { series, axis, mode, first, mouse } = this;
    if (!series || mode === "select") return;

    target.useMediaCoordinateSpace(({ context, mediaSize }) => {
      context.lineWidth = 1;

      if (mode === "horizontal") {
        if (!mouse) return;
        context.setLineDash([6, 4]);
        context.strokeStyle = "rgba(21, 101, 192, 0.6)";
        context.beginPath();
        context.moveTo(0, mouse.y);
        context.lineTo(mediaSize.width, mouse.y);
        context.stroke();
        return;
      }

      if (!first || !axis) return;
      const x1 = axis.dateToX(first.time);
      const y1 = series.priceToCoordinate(first.price);
      if (x1 === null || y1 === null) return;

      if (mouse) {
        context.setLineDash([6, 4]);
        if (mode === "trend") {
          context.strokeStyle = "rgba(198, 40, 40, 0.6)";
          context.beginPath();
          context.moveTo(x1, y1);
          context.lineTo(mouse.x, mouse.y);
          context.stroke();
        } else if (mode === "zone") {
          const x = Math.min(x1, mouse.x);
          const y = Math.min(y1, mouse.y);
          const w = Math.abs(mouse.x - x1);
          const h = Math.abs(mouse.y - y1);
          context.fillStyle = "rgba(33, 150, 243, 0.12)";
          context.fillRect(x, y, w, h);
          context.strokeStyle = "rgba(33, 150, 243, 0.7)";
          context.strokeRect(x + 0.5, y + 0.5, Math.max(w - 1, 0), Math.max(h - 1, 0));
        }
        context.setLineDash([]);
      }

      // 첫 점: 주황 점 + "1"
      context.fillStyle = "#ff9800";
      context.beginPath();
      context.arc(x1, y1, 6, 0, Math.PI * 2);
      context.fill();
      context.fillStyle = "#ffffff";
      context.font = "bold 9px sans-serif";
      context.textAlign = "center";
      context.textBaseline = "middle";
      context.fillText("1", x1, y1 + 0.5);
    });
  }
}
