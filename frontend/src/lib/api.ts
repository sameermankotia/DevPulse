import type { Health, Insight, PullRequestRow, Repository, Snapshot } from './types'

const BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

/** An API failure carrying the server's own explanation, not a generic string. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...init,
    })
  } catch {
    throw new ApiError('The service is unreachable. Check that the API is running.', 0)
  }

  if (!response.ok) {
    const detail = await response
      .json()
      .then((body: { detail?: string }) => body.detail)
      .catch(() => undefined)
    throw new ApiError(
      detail ?? `Request failed with status ${response.status}`,
      response.status,
    )
  }

  return (await response.json()) as T
}

export const api = {
  health: () => request<Health>('/health'),

  repositories: () => request<Repository[]>('/repositories'),

  snapshot: (repositoryId: number, windowDays: number) =>
    request<Snapshot>(`/repositories/${repositoryId}/snapshot?window_days=${windowDays}`),

  pullRequests: (repositoryId: number, windowDays: number, limit = 50) =>
    request<PullRequestRow[]>(
      `/repositories/${repositoryId}/pull-requests?window_days=${windowDays}&limit=${limit}`,
    ),

  latestInsight: (repositoryId: number) =>
    request<Insight | null>(`/repositories/${repositoryId}/insights`),

  generateInsight: (repositoryId: number, windowDays: number, force = false) =>
    request<Insight>(
      `/repositories/${repositoryId}/insights?window_days=${windowDays}&force=${force}`,
      { method: 'POST' },
    ),
}
