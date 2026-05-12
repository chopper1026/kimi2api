import { useState, useEffect } from "react"
import { useParams, useNavigate } from "react-router-dom"
import { api } from "@/lib/api-client"
import type { LogDetailData } from "@/types"
import { Button } from "@/components/ui/button"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { DetailSkeleton } from "@/components/shared/PageSkeletons"
import { JsonTreeView } from "@/components/logs/JsonTreeView"
import { ArrowLeftIcon } from "lucide-react"

function parseJsonObject(value: string): Record<string, unknown> | null {
  try {
    const parsed: unknown = JSON.parse(value)
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>
    }
  } catch {
    return null
  }
  return null
}

export default function LogDetailPage() {
  const { requestId } = useParams<{ requestId: string }>()
  const navigate = useNavigate()
  const [data, setData] = useState<LogDetailData | null>(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)

  useEffect(() => {
    if (!requestId) return
    setLoading(true)
    setNotFound(false)
    api
      .getLogDetail(requestId)
      .then((d) => setData(d))
      .catch((err) => {
        if (err?.status === 404) {
          setNotFound(true)
        }
      })
      .finally(() => setLoading(false))
  }, [requestId])

  if (loading) {
    return <DetailSkeleton />
  }

  if (notFound || !data) {
    return (
      <div className="py-16 text-center text-muted-foreground">
        未找到该日志
      </div>
    )
  }

  const isSuccess = data.status_code < 400
  const shouldShowParsedResponse = Boolean(
    data.is_stream || data.parsed_response_text || data.parsed_reasoning_content,
  )

  const parsedHeaders = data.request_headers
    ? parseJsonObject(data.request_headers)
    : null
  const parsedRespHeaders = data.response_headers
    ? parseJsonObject(data.response_headers)
    : null

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <Button
          variant="ghost"
          size="icon"
          className="size-8"
          onClick={() => navigate(-1)}
        >
          <ArrowLeftIcon className="size-4" />
        </Button>
        <h2 className="truncate font-mono text-xs text-muted-foreground">
          {data.request_id}
        </h2>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Card className="border-border/60 shadow-sm">
          <CardContent className="pt-4 pb-4">
            <p className="text-[11px] text-muted-foreground">状态</p>
            <div className="mt-1 flex items-center gap-2">
              <span
                className={`text-xl font-bold ${
                  isSuccess ? "text-success" : "text-destructive"
                }`}
              >
                {data.status_code}
              </span>
              <Badge
                variant={isSuccess ? "default" : "destructive"}
                className="text-[10px]"
              >
                {data.status}
              </Badge>
            </div>
          </CardContent>
        </Card>
        <Card className="border-border/60 shadow-sm">
          <CardContent className="pt-4 pb-4">
            <p className="text-[11px] text-muted-foreground">耗时</p>
            <p className="mt-1 text-xl font-bold">{data.duration_display}</p>
          </CardContent>
        </Card>
        <Card className="border-border/60 shadow-sm">
          <CardContent className="pt-4 pb-4">
            <p className="text-[11px] text-muted-foreground">类型</p>
            <p className="mt-1 text-xl font-bold">
              {data.is_stream ? "流式" : "普通"}
            </p>
          </CardContent>
        </Card>
        <Card className="border-border/60 shadow-sm">
          <CardContent className="pt-4 pb-4">
            <p className="text-[11px] text-muted-foreground">Key 名称</p>
            <p className="mt-1 text-xl font-bold truncate">
              {data.api_key_name || "-"}
            </p>
          </CardContent>
        </Card>
      </div>

      <Card className="border-border/60 shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium">元数据</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 text-xs">
            <div>
              <span className="text-muted-foreground">时间：</span>
              {data.time_str}
            </div>
            <div>
              <span className="text-muted-foreground">模型：</span>
              {data.model || "-"}
            </div>
            <div>
              <span className="text-muted-foreground">请求：</span>
              <span className="font-mono">
                {data.method} {data.path}
              </span>
            </div>
            <div>
              <span className="text-muted-foreground">URL：</span>
              <span className="font-mono text-[11px] break-all">{data.url}</span>
            </div>
            <div>
              <span className="text-muted-foreground">客户端 IP：</span>
              <span className="font-mono">{data.client_ip || "-"}</span>
            </div>
            <div>
              <span className="text-muted-foreground">User-Agent：</span>
              <span className="text-[11px] break-all">
                {data.user_agent || "-"}
              </span>
            </div>
          </div>
          {data.upstream_summary && (
            <div className="mt-3 rounded-lg border border-warning/35 bg-warning-muted/25 px-3 py-2 text-xs text-warning">
              <span className="font-medium">上游信息：</span>
              {data.upstream_summary}
            </div>
          )}
          {data.error_message && (
            <div className="mt-3 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
              <span className="font-medium">错误：</span>
              {data.error_message}
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="border-border/60 shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium">请求信息</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <p className="mb-1.5 text-[11px] font-medium text-muted-foreground">
              请求头
            </p>
            {parsedHeaders ? (
              <div className="rounded-lg bg-muted/50 p-3 overflow-auto max-h-64">
                <pre className="font-mono text-[11px] whitespace-pre-wrap">
                  {JSON.stringify(parsedHeaders, null, 2)}
                </pre>
              </div>
            ) : data.request_headers ? (
              <div className="rounded-lg bg-muted/50 p-3 overflow-auto max-h-64">
                <pre className="font-mono text-[11px] whitespace-pre-wrap">
                  {data.request_headers}
                </pre>
              </div>
            ) : (
              <p className="text-[11px] text-muted-foreground">无数据</p>
            )}
          </div>
          <div>
            <p className="mb-1.5 text-[11px] font-medium text-muted-foreground">
              请求体
              {data.request_body_truncated && (
                <span className="ml-2 text-warning">（已截断）</span>
              )}
            </p>
            {data.request_body_is_json ? (
              <div className="rounded-lg bg-muted/50 p-3 overflow-auto max-h-96">
                <JsonTreeView value={data.request_body_json} />
              </div>
            ) : data.request_body ? (
              <div className="rounded-lg bg-muted/50 p-3 overflow-auto max-h-96">
                <pre className="font-mono text-[11px] whitespace-pre-wrap">
                  {data.request_body}
                </pre>
              </div>
            ) : (
              <p className="text-[11px] text-muted-foreground">无数据</p>
            )}
          </div>
        </CardContent>
      </Card>

      <Card className="border-border/60 shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium">响应信息</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <p className="mb-1.5 text-[11px] font-medium text-muted-foreground">
              响应头
            </p>
            {parsedRespHeaders ? (
              <div className="rounded-lg bg-muted/50 p-3 overflow-auto max-h-64">
                <pre className="font-mono text-[11px] whitespace-pre-wrap">
                  {JSON.stringify(parsedRespHeaders, null, 2)}
                </pre>
              </div>
            ) : data.response_headers ? (
              <div className="rounded-lg bg-muted/50 p-3 overflow-auto max-h-64">
                <pre className="font-mono text-[11px] whitespace-pre-wrap">
                  {data.response_headers}
                </pre>
              </div>
            ) : (
              <p className="text-[11px] text-muted-foreground">无数据</p>
            )}
          </div>
          {shouldShowParsedResponse && (
            <>
              <div>
                <p className="mb-1.5 text-[11px] font-medium text-muted-foreground">
                  解析正文
                </p>
                <div className="rounded-lg bg-muted/50 p-3 overflow-auto max-h-96">
                  <pre className="font-mono text-[11px] whitespace-pre-wrap break-all">
                    {data.parsed_response_text || "-"}
                  </pre>
                </div>
              </div>
              <div>
                <p className="mb-1.5 text-[11px] font-medium text-muted-foreground">
                  思维链
                </p>
                <div className="rounded-lg bg-muted/50 p-3 overflow-auto max-h-96">
                  <pre className="font-mono text-[11px] whitespace-pre-wrap break-all">
                    {data.parsed_reasoning_content || "-"}
                  </pre>
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
