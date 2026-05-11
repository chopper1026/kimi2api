export interface SessionInfo {
  authenticated: boolean
  csrf_token?: string
  enabled?: boolean
}

export interface DashboardStats {
  uptime: string
  token_healthy: boolean
  token_status: string
  token_type: string
  token_expires: string
  key_count: number
  total_requests: number
  log_count: number
}

export interface TokenInfo {
  token_type: string
  token_expires: string
  token_preview: string
  token_healthy: boolean
  token_status: string
}

export interface TokenSaveResult {
  success: boolean
  message?: string
  error?: string
  token: TokenInfo
}

export interface TokenValidation {
  valid: boolean
  subscription: Record<string, unknown>
}

export interface KeyItem {
  key: string
  key_preview: string
  name: string
  created_at_str: string
  last_used_str: string
  request_count: number
}

export interface KeysResponse {
  keys: KeyItem[]
  new_key?: string
  deleted?: boolean
}

export interface LogEntry {
  request_id: string
  request_id_short: string
  time_str: string
  api_key_name: string
  model: string
  method: string
  path: string
  status: string
  status_code: number
  duration_ms: number
  duration_display: string
  is_stream: boolean
  error_message: string
  upstream_status_code: number
  upstream_error_type: string
  upstream_retry_after: number
  upstream_summary: string
}

export interface Pagination {
  total: number
  page: number
  page_count: number
  page_size: number
  start_index: number
  end_index: number
  has_prev: boolean
  has_next: boolean
  prev_url: string
  next_url: string
  first_url: string
  last_url: string
}

export interface LogsPage {
  logs: LogEntry[]
  pagination: Pagination
}

export interface LogFilters {
  q: string
  status: string
  model: string
  api_key_name: string
  path: string
  stream: string
  page: string
}

export interface LogDetailData {
  request_id: string
  time_str: string
  method: string
  path: string
  url: string
  query_params: string
  client_ip: string
  user_agent: string
  api_key_name: string
  model: string
  status: string
  status_code: number
  duration_ms: number
  duration_display: string
  is_stream: boolean
  error_message: string
  upstream_status_code: number
  upstream_error_type: string
  upstream_retry_after: number
  upstream_summary: string
  request_headers: string
  request_body: string
  request_body_is_json: boolean
  request_body_json: unknown
  request_body_truncated: boolean
  response_headers: string
  raw_stream_body: string
  parsed_response_text: string
  parsed_reasoning_content: string
}

export interface ApiError {
  error: string
  success?: boolean
}
