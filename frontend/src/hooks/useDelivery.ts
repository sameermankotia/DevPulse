import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError, api } from '@/lib/api'

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: api.health,
    staleTime: 60_000,
  })
}

export function useRepositories() {
  return useQuery({
    queryKey: ['repositories'],
    queryFn: api.repositories,
    staleTime: 60_000,
  })
}

export function useSnapshot(repositoryId: number | null, windowDays: number) {
  return useQuery({
    queryKey: ['snapshot', repositoryId, windowDays],
    queryFn: () => api.snapshot(repositoryId!, windowDays),
    enabled: repositoryId !== null,
    // The window is the expensive part of the query; keep the previous view on
    // screen while a new one loads instead of flashing a skeleton.
    placeholderData: (previous) => previous,
  })
}

export function usePullRequests(repositoryId: number | null, windowDays: number) {
  return useQuery({
    queryKey: ['pull-requests', repositoryId, windowDays],
    queryFn: () => api.pullRequests(repositoryId!, windowDays),
    enabled: repositoryId !== null,
    placeholderData: (previous) => previous,
  })
}

export function useInsight(repositoryId: number | null) {
  return useQuery({
    queryKey: ['insight', repositoryId],
    queryFn: () => api.latestInsight(repositoryId!),
    enabled: repositoryId !== null,
  })
}

export function useGenerateInsight(repositoryId: number | null, windowDays: number) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: () => api.generateInsight(repositoryId!, windowDays, true),
    onSuccess: (insight) => {
      queryClient.setQueryData(['insight', repositoryId], insight)
    },
  })
}

/** Turns any thrown value into a sentence worth showing a person. */
export function errorMessage(error: unknown): string | null {
  if (!error) return null
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return 'Something went wrong. Try again.'
}
