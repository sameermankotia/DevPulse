import { formatRelativeTime } from '@/lib/format'
import type { Repository } from '@/lib/types'
import './Header.css'

interface Props {
  repositories: Repository[]
  selectedId: number | null
  onSelect: (id: number) => void
  windowDays: number
  onWindowChange: (days: number) => void
}

const WINDOWS = [14, 30, 60, 90]

export function Header({
  repositories,
  selectedId,
  onSelect,
  windowDays,
  onWindowChange,
}: Props) {
  const selected = repositories.find((repo) => repo.id === selectedId)

  return (
    <header className="header">
      <div className="shell header__inner">
        <a href="#main" className="header__brand">
          DevPulse
        </a>

        {repositories.length > 0 && (
          <div className="header__controls">
            <label htmlFor="repo-select" className="visually-hidden">
              Repository
            </label>
            <select
              id="repo-select"
              className="header__select"
              value={selectedId ?? ''}
              onChange={(event) => onSelect(Number(event.target.value))}
            >
              {repositories.map((repo) => (
                <option key={repo.id} value={repo.id}>
                  {repo.full_name}
                </option>
              ))}
            </select>

            <div className="header__windows" role="group" aria-label="Time window">
              {WINDOWS.map((days) => (
                <button
                  key={days}
                  type="button"
                  className="header__window"
                  aria-pressed={windowDays === days}
                  onClick={() => onWindowChange(days)}
                >
                  {days}d
                </button>
              ))}
            </div>

            {selected && (
              <span className="header__synced">
                Synced {formatRelativeTime(selected.last_synced_at)}
              </span>
            )}
          </div>
        )}
      </div>
    </header>
  )
}
