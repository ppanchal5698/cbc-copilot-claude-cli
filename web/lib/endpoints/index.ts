/** Typed API path builders for the authenticated proxy. */

export const endpoints = {
  jobCancel: (jobId: string) => `/api/proxy/jobs/${jobId}/cancel`,
  pipelineSettings: () => "/api/proxy/settings/pipeline",
  freshnessSettings: () => "/api/proxy/settings/freshness",
  integrations: () => "/api/proxy/integrations",
  projectDelete: (code: string) => `/api/proxy/projects/${encodeURIComponent(code)}`,
  proposalPdf: (code: string) => `/api/proxy/projects/${code}/proposal/pdf`,
  proposalRender: (code: string) => `/api/proxy/projects/${code}/proposal/render`,
  jobTerminal: (jobId: string) => `/api/proxy/jobs/${jobId}/terminal`,
  claudeOauthCode: () => "/api/proxy/settings/claude/oauth/code",
  jobMetrics: (hours = 24) => `/api/proxy/jobs/metrics?hours=${hours}`,
} as const;
