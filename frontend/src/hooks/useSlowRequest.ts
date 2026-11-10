import { useEffect, useState } from 'react'

/**
 * True once `active` has been running longer than `afterMs`.
 *
 * Used to explain a wait rather than let it look like a hang: the free hosting
 * tier sleeps idle instances, so the first request of the day really does take
 * the better part of a minute.
 */
export function useSlowRequest(active: boolean, afterMs = 5000): boolean {
  const [slow, setSlow] = useState(false)

  useEffect(() => {
    if (!active) {
      setSlow(false)
      return
    }
    const timer = window.setTimeout(() => setSlow(true), afterMs)
    return () => window.clearTimeout(timer)
  }, [active, afterMs])

  return slow
}
