import { useId, useMemo, useState } from 'react'

import { formatDate } from '@/lib/format'
import type { MetricPoint } from '@/lib/types'
import './Sparkline.css'

interface Props {
  points: MetricPoint[]
  /** Formats the value shown in the hover readout. */
  format: (value: number) => string
  label: string
}

const WIDTH = 240
const HEIGHT = 56
const PAD = 4

/**
 * A single-series trend line. One series means no legend: the tile's own title
 * names it. Hover exposes the exact value, so no point carries a printed number.
 */
export function Sparkline({ points, format, label }: Props) {
  const gradientId = useId()
  const [active, setActive] = useState<number | null>(null)

  const geometry = useMemo(() => {
    if (points.length < 2) return null

    const values = points.map((p) => p.value)
    const min = Math.min(...values)
    const max = Math.max(...values)
    // A flat series would divide by zero; give it a centred band instead.
    const span = max - min || Math.abs(max) || 1

    const coords = points.map((point, index) => ({
      x: PAD + (index / (points.length - 1)) * (WIDTH - PAD * 2),
      y: HEIGHT - PAD - ((point.value - min) / span) * (HEIGHT - PAD * 2),
      point,
    }))

    const line = coords.map(
      (c, i) => `${i === 0 ? 'M' : 'L'}${c.x.toFixed(2)} ${c.y.toFixed(2)}`,
    )
    const area = `${line.join(' ')} L${coords[coords.length - 1]!.x.toFixed(2)} ${HEIGHT} L${coords[0]!.x.toFixed(2)} ${HEIGHT} Z`

    return { coords, line: line.join(' '), area }
  }, [points])

  if (!geometry) {
    return <div className="spark spark--empty" aria-hidden="true" />
  }

  const activeCoord = active !== null ? geometry.coords[active] : null
  // The line stays neutral ink. Whether the trend is good news is stated once,
  // by the trend row above it -- encoding it twice invites the two to disagree.
  const tone = 'var(--content-secondary)'

  return (
    <div className="spark">
      <svg
        className="spark__svg"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={`${label}: ${points.length} daily points from ${formatDate(points[0]!.at)} to ${formatDate(points[points.length - 1]!.at)}.`}
        onMouseLeave={() => setActive(null)}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={tone} stopOpacity="0.22" />
            <stop offset="100%" stopColor={tone} stopOpacity="0" />
          </linearGradient>
        </defs>

        <path d={geometry.area} fill={`url(#${gradientId})`} />
        <path
          d={geometry.line}
          fill="none"
          stroke={tone}
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          vectorEffect="non-scaling-stroke"
        />

        {activeCoord && (
          <>
            <line
              x1={activeCoord.x}
              y1={0}
              x2={activeCoord.x}
              y2={HEIGHT}
              stroke="var(--hairline-strong)"
              strokeWidth="1"
              vectorEffect="non-scaling-stroke"
            />
            {/* A 2px surface ring keeps the marker readable over the fill. */}
            <circle
              cx={activeCoord.x}
              cy={activeCoord.y}
              r="4"
              fill={tone}
              stroke="var(--surface-elevated)"
              strokeWidth="2"
              vectorEffect="non-scaling-stroke"
            />
          </>
        )}
      </svg>

      {/* Hit targets are wider than the marks, per the interaction spec. */}
      <div className="spark__hits">
        {geometry.coords.map((coord, index) => (
          <button
            key={coord.point.at}
            type="button"
            className="spark__hit"
            onMouseEnter={() => setActive(index)}
            onFocus={() => setActive(index)}
            onBlur={() => setActive(null)}
            tabIndex={-1}
            aria-hidden="true"
          />
        ))}
      </div>

      <p className="spark__readout" aria-hidden="true">
        {activeCoord
          ? `${formatDate(activeCoord.point.at)} · ${format(activeCoord.point.value)}`
          : ' '}
      </p>
    </div>
  )
}
