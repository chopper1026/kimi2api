import { useState, useEffect, useCallback } from "react"
import { useSearchParams, useNavigate } from "react-router-dom"
import { api } from "@/lib/api-client"
import type { LogEntry, LogsPage } from "@/types"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table"
import {
  SearchIcon,
  RotateCcwIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ChevronsLeftIcon,
  ChevronsRightIcon,
  FileTextIcon,
} from "lucide-react"

function requestIdPreview(log: LogEntry) {
  return log.request_id_short.length < log.request_id.length
    ? `${log.request_id_short}...`
    : log.request_id_short
}

function logModelLabel(log: LogEntry) {
  if (log.path === "/v1/models" && log.model === "unknown") {
    return ""
  }
  return log.model || ""
}

export default function LogsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [pagination, setPagination] = useState<LogsPage["pagination"] | null>(
    null,
  )
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const q = searchParams.get("q") ?? ""
  const status = searchParams.get("status") ?? ""
  const stream = searchParams.get("stream") ?? ""
  const model = searchParams.get("model") ?? ""
  const api_key_name = searchParams.get("api_key_name") ?? ""
  const path = searchParams.get("path") ?? ""
  const page = searchParams.get("page") ?? "1"

  const fetchLogs = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const filters: Record<string, string> = {}
      if (q) filters.q = q
      if (status) filters.status = status
      if (stream) filters.stream = stream
      if (model) filters.model = model
      if (api_key_name) filters.api_key_name = api_key_name
      if (path) filters.path = path
      filters.page = page
      const data = await api.getLogs(filters)
      setLogs(data.logs)
      setPagination(data.pagination)
    } catch {
      setError("加载日志失败")
    } finally {
      setLoading(false)
    }
  }, [q, status, stream, model, api_key_name, path, page])

  useEffect(() => {
    fetchLogs()
  }, [fetchLogs])

  const updateFilter = (name: string, value: string) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (value) {
        next.set(name, value)
      } else {
        next.delete(name)
      }
      next.set("page", "1")
      return next
    })
  }

  const handleClear = () => {
    setSearchParams({})
  }

  const goToPage = (p: number) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.set("page", String(p))
      return next
    })
  }

  const _qp = (url: string | null) => {
    if (!url) return 1
    try {
      const u = new URL(url, "http://dummy")
      return Number(u.searchParams.get("page") ?? "1")
    } catch {
      return 1
    }
  }

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="rounded-lg border border-border/60 bg-card p-4 shadow-sm">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-[minmax(220px,1.4fr)_minmax(132px,0.8fr)_minmax(132px,0.8fr)_minmax(150px,1fr)_minmax(150px,1fr)_minmax(150px,1fr)]">
          <Input
            name="q"
            placeholder="关键词搜索"
            value={q}
            onChange={(e) => updateFilter("q", e.target.value)}
            className="h-8 min-w-0 text-xs"
          />
          <Select
            value={status || ""}
            onValueChange={(v) => updateFilter("status", v === "__all__" ? "" : (v ?? ""))}
          >
            <SelectTrigger className="h-8 w-full min-w-0 text-xs">
              <SelectValue placeholder="状态：全部" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">全部状态</SelectItem>
              <SelectItem value="success">成功</SelectItem>
              <SelectItem value="error">错误</SelectItem>
            </SelectContent>
          </Select>
          <Select
            value={stream || ""}
            onValueChange={(v) => updateFilter("stream", v === "__all__" ? "" : (v ?? ""))}
          >
            <SelectTrigger className="h-8 w-full min-w-0 text-xs">
              <SelectValue placeholder="类型：全部" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">全部类型</SelectItem>
              <SelectItem value="true">流式</SelectItem>
              <SelectItem value="false">普通</SelectItem>
            </SelectContent>
          </Select>
          <Input
            name="model"
            placeholder="模型"
            value={model}
            onChange={(e) => updateFilter("model", e.target.value)}
            className="h-8 min-w-0 text-xs"
          />
          <Input
            name="api_key_name"
            placeholder="Key 名称"
            value={api_key_name}
            onChange={(e) => updateFilter("api_key_name", e.target.value)}
            className="h-8 min-w-0 text-xs"
          />
          <Input
            name="path"
            placeholder="路径"
            value={path}
            onChange={(e) => updateFilter("path", e.target.value)}
            className="h-8 min-w-0 text-xs"
          />
        </div>
        <div className="mt-2.5 flex gap-2">
          <Button size="sm" className="h-7 text-xs" onClick={fetchLogs}>
            <SearchIcon className="mr-1 size-3" />
            筛选
          </Button>
          <Button size="sm" variant="outline" className="h-7 text-xs" onClick={handleClear}>
            <RotateCcwIcon className="mr-1 size-3" />
            清空
          </Button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      ) : logs.length === 0 ? (
        <div className="rounded-lg border border-border/60 bg-card py-16 text-center shadow-sm">
          <FileTextIcon className="mx-auto size-8 text-muted-foreground/30" />
          <p className="mt-3 text-sm text-muted-foreground">暂无请求记录</p>
        </div>
      ) : (
        <>
          <div className="rounded-lg border border-border/60 bg-card shadow-sm overflow-hidden">
            <Table className="min-w-[900px] table-fixed">
              <colgroup>
                <col className="w-28" />
                <col className="w-28" />
                <col className="w-32" />
                <col />
                <col className="w-36" />
                <col className="w-[88px]" />
                <col className="w-20" />
                <col className="w-20" />
              </colgroup>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="text-xs">时间</TableHead>
                  <TableHead className="text-xs">Request ID</TableHead>
                  <TableHead className="text-xs">Key</TableHead>
                  <TableHead className="text-xs">请求</TableHead>
                  <TableHead className="text-xs">模型</TableHead>
                  <TableHead className="text-xs">状态</TableHead>
                  <TableHead className="text-xs">耗时</TableHead>
                  <TableHead className="text-left text-xs">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {logs.map((log) => (
                  <TableRow key={log.request_id}>
                    <TableCell className="text-xs text-muted-foreground">
                      {log.time_str}
                    </TableCell>
                    <TableCell>
                      <code
                        className="block truncate text-[11px] text-muted-foreground"
                        title={log.request_id}
                      >
                        {requestIdPreview(log)}
                      </code>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {log.api_key_name || "-"}
                    </TableCell>
                    <TableCell>
                      <div className="truncate text-xs">
                        <span className="font-medium text-muted-foreground">
                          {log.method}
                        </span>{" "}
                        {log.path}
                      </div>
                      {log.error_message && (
                        <div className="mt-0.5 text-[11px] text-destructive truncate max-w-48">
                          {log.error_message}
                        </div>
                      )}
                      {log.upstream_summary && (
                        <div className="mt-0.5 text-[11px] text-amber-600 truncate max-w-48">
                          {log.upstream_summary}
                        </div>
                      )}
                    </TableCell>
                    <TableCell className="truncate text-xs text-muted-foreground">
                      {logModelLabel(log)}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <span
                          className={`text-xs font-medium ${
                            log.status_code >= 400
                              ? "text-destructive"
                              : "text-emerald-600"
                          }`}
                        >
                          {log.status_code}
                        </span>
                        {log.is_stream && (
                          <Badge variant="secondary" className="text-[10px] px-1 py-0">
                            流式
                          </Badge>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {log.duration_display}
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="outline"
                        size="xs"
                        onClick={() => navigate(`/admin/logs/${log.request_id}`)}
                        title="查看详情"
                        className="h-7 px-2.5 text-[11px]"
                      >
                        详情
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          {pagination && (
            <div className="flex items-center justify-between">
              <p className="text-xs text-muted-foreground">
                第 {pagination.start_index}-{pagination.end_index} 条，共{" "}
                {pagination.total} 条
              </p>
              <div className="flex items-center gap-1">
                <Button
                  variant="outline"
                  size="icon-xs"
                  disabled={!pagination.has_prev}
                  onClick={() => goToPage(1)}
                  title="首页"
                >
                  <ChevronsLeftIcon className="size-3.5" />
                </Button>
                <Button
                  variant="outline"
                  size="icon-xs"
                  disabled={!pagination.has_prev}
                  onClick={() => goToPage(_qp(pagination.prev_url))}
                  title="上一页"
                >
                  <ChevronLeftIcon className="size-3.5" />
                </Button>
                <span className="px-2 text-xs text-muted-foreground">
                  {pagination.page} / {pagination.page_count}
                </span>
                <Button
                  variant="outline"
                  size="icon-xs"
                  disabled={!pagination.has_next}
                  onClick={() => goToPage(_qp(pagination.next_url))}
                  title="下一页"
                >
                  <ChevronRightIcon className="size-3.5" />
                </Button>
                <Button
                  variant="outline"
                  size="icon-xs"
                  disabled={!pagination.has_next}
                  onClick={() => goToPage(pagination.page_count)}
                  title="末页"
                >
                  <ChevronsRightIcon className="size-3.5" />
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
