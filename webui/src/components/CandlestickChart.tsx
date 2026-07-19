import { useMemo, useState } from "react";
import { formatDate, sideLabel } from "../locale";
import type { SecurityBar, TradeMarker } from "../types";

const WIDTH = 1000;
const PRICE_TOP = 24;
const PRICE_BOTTOM = 292;
const VOLUME_TOP = 322;
const VOLUME_BOTTOM = 400;
const LEFT = 58;
const RIGHT = 18;

function money(value: number) {
  return value.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function CandlestickChart({
  bars,
  markers,
}: {
  bars: SecurityBar[];
  markers: TradeMarker[];
}) {
  const [hovered, setHovered] = useState<number | null>(null);
  const dates = useMemo(
    () => [...new Set([...bars.map((bar) => bar.date), ...markers.map((marker) => marker.date)])].sort(),
    [bars, markers],
  );
  if (!bars.length) {
    return <div className="chart-empty">该证券没有已记录的 K 线证据。</div>;
  }
  const low = Math.min(...bars.map((bar) => bar.low), ...markers.map((marker) => marker.price));
  const high = Math.max(...bars.map((bar) => bar.high), ...markers.map((marker) => marker.price));
  const priceRange = high - low || 1;
  const maxVolume = Math.max(...bars.map((bar) => bar.volume), 1);
  const step = (WIDTH - LEFT - RIGHT) / Math.max(dates.length, 1);
  const candleWidth = Math.max(4, Math.min(18, step * 0.56));
  const x = (barDate: string) => LEFT + (dates.indexOf(barDate) + 0.5) * step;
  const y = (price: number) => PRICE_BOTTOM - ((price - low) / priceRange) * (PRICE_BOTTOM - PRICE_TOP);
  const active = hovered == null ? bars.at(-1) : bars[hovered];

  return (
    <div className="candlestick-chart">
      <div className="ohlc-strip" aria-live="polite">
        <span>{formatDate(active?.date)}</span>
        <b>开 {money(active?.open ?? 0)}</b>
        <b>高 {money(active?.high ?? 0)}</b>
        <b>低 {money(active?.low ?? 0)}</b>
        <b>收 {money(active?.close ?? 0)}</b>
        <span>成交量 {(active?.volume ?? 0).toLocaleString("zh-CN")}</span>
      </div>
      <svg viewBox={`0 0 ${WIDTH} 430`} role="img" aria-label="带买卖标记的 K 线图">
        {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
          const gridY = PRICE_TOP + ratio * (PRICE_BOTTOM - PRICE_TOP);
          const label = high - ratio * priceRange;
          return (
            <g key={ratio}>
              <line x1={LEFT} x2={WIDTH - RIGHT} y1={gridY} y2={gridY} className="chart-grid" />
              <text x={LEFT - 8} y={gridY + 4} textAnchor="end" className="chart-tick">{money(label)}</text>
            </g>
          );
        })}
        {bars.map((bar, index) => {
          const rising = bar.close >= bar.open;
          const candleX = x(bar.date);
          const bodyTop = y(Math.max(bar.open, bar.close));
          const bodyBottom = y(Math.min(bar.open, bar.close));
          const volumeHeight = (bar.volume / maxVolume) * (VOLUME_BOTTOM - VOLUME_TOP);
          return (
            <g
              key={`${bar.date}-${index}`}
              className={`candle ${rising ? "up" : "down"}`}
              onMouseEnter={() => setHovered(index)}
              onMouseLeave={() => setHovered(null)}
            >
              <rect x={candleX - step / 2} y={PRICE_TOP} width={step} height={VOLUME_BOTTOM - PRICE_TOP} fill="transparent" />
              <line x1={candleX} x2={candleX} y1={y(bar.high)} y2={y(bar.low)} />
              <rect
                x={candleX - candleWidth / 2}
                y={bodyTop}
                width={candleWidth}
                height={Math.max(bodyBottom - bodyTop, 2)}
              />
              <rect
                className="volume-bar"
                x={candleX - candleWidth / 2}
                y={VOLUME_BOTTOM - volumeHeight}
                width={candleWidth}
                height={volumeHeight}
              />
            </g>
          );
        })}
        {markers.map((marker, index) => {
          const markerX = x(marker.date);
          const markerY = y(marker.price);
          const buy = marker.side === "buy";
          return (
            <g
              key={`${marker.date}-${marker.side}-${index}`}
              className={`trade-marker ${buy ? "buy" : "sell"}`}
              aria-label={`${sideLabel(marker.side)} ${marker.quantity} 股，价格 ${money(marker.price)}，日期 ${formatDate(marker.date)}`}
            >
              <path
                d={buy
                  ? `M ${markerX} ${markerY - 5} l -8 13 h 16 z`
                  : `M ${markerX} ${markerY + 5} l -8 -13 h 16 z`}
              />
              <text x={markerX + 11} y={markerY + 4}>{buy ? "买" : "卖"}</text>
            </g>
          );
        })}
        {hovered != null ? (
          <line
            x1={x(bars[hovered].date)}
            x2={x(bars[hovered].date)}
            y1={PRICE_TOP}
            y2={VOLUME_BOTTOM}
            className="chart-crosshair"
          />
        ) : null}
      </svg>
      <div className="chart-axis">
        <span>{formatDate(dates[0])}</span>
        <span>已记录证据 · 日线 OHLCV</span>
        <span>{formatDate(dates.at(-1))}</span>
      </div>
    </div>
  );
}
