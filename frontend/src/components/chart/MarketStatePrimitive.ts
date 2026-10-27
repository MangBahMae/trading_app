import type {
  ISeriesPrimitive, ISeriesPrimitivePaneRenderer, ISeriesPrimitivePaneView, SeriesAttachedParameter, Time,
} from "lightweight-charts";
import type { MarketStateBlock } from "../../types";
import { MARKET_STATE_COLORS, marketStateBlockSpan } from "./chartLogic";
import type { TimeAxis } from "./timeAxis";

type DrawTarget = Parameters<ISeriesPrimitivePaneRenderer["draw"]>[0];

// 시장 상태(횡보) 배경 음영 - 시리즈 프리미티브로 pane 전체 높이의 세로 띠를 그린다.
// zOrder "bottom"이라 캔들/존/선 아래에 깔리고, 좌표는 그릴 때마다 TimeAxis(차트 timeScale)에서
// 다시 구하므로 줌/스크롤을 따라간다. 신호가 아니라 보기용이다. setData([])면 아무것도 안 그린다(토글 OFF).
export class MarketStatePrimitive implements ISeriesPrimitive<Time> {
  private requestUpdate: (() => void) | null = null;
  private readonly view: ISeriesPrimitivePaneView;
  private blocks: MarketStateBlock[] = [];
  private axis: TimeAxis | null = null;

  constructor() {
    this.view = {
      zOrder: () => "bottom",
      renderer: () => ({ draw: (target: DrawTarget) => this.draw(target) }),
    };
  }

  attached(param: SeriesAttachedParameter<Time>): void {
    this.requestUpdate = param.requestUpdate;
  }

  detached(): void {
    this.requestUpdate = null;
  }

  paneViews(): readonly ISeriesPrimitivePaneView[] {
    return [this.view];
  }

  setData(blocks: MarketStateBlock[], axis: TimeAxis): void {
    this.blocks = blocks;
    this.axis = axis;
    this.requestUpdate?.();
  }

  private draw(target: DrawTarget): void {
    const axis = this.axis;
    if (!axis || this.blocks.length === 0) return;
    target.useMediaCoordinateSpace(({ context, mediaSize }) => {
      for (const block of this.blocks) {
        const span = marketStateBlockSpan(block.start, block.end, axis.dateToX);
        if (!span) continue;
        context.fillStyle = MARKET_STATE_COLORS[block.reason];
        context.fillRect(span[0], 0, span[1] - span[0], mediaSize.height);
      }
    });
  }
}
