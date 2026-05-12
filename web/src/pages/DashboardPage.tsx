import type { ReactNode } from "react"
import { useNavigate } from "react-router-dom"
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock,
  Database,
  FileText,
  Key,
  Pencil,
  Plus,
  Radio,
  Settings2,
  Shield,
  XCircle,
} from "lucide-react"

import { usePolling } from "@/hooks/use-polling"
import { api } from "@/lib/api-client"
import type { DashboardStats, RecentError } from "@/types"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"

interface StatCardProps {
  icon: ReactNode
  title: string
  value: ReactNode
  detail?: ReactNode
  loading: boolean
}

function StatCard({ icon, title, value, detail, loading }: StatCardProps) {
  return (
    <Card className="border-border/60 shadow-sm">
      <CardContent className="pt-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[11px] font-medium text-muted-foreground">
              {title}
            </p>
            {loading ? (
              <Skeleton className="mt-2 h-7 w-24" />
            ) : (
              <div className="mt-1 truncate text-2xl font-bold tracking-tight">
                {value}
              </div>
            )}
          </div>
          <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            {icon}
          </div>
        </div>
        {loading ? (
          <Skeleton className="mt-3 h-4 w-32" />
        ) : detail ? (
          <div className="mt-2 text-xs text-muted-foreground">{detail}</div>
        ) : null}
      </CardContent>
    </Card>
  )
}

function ActivityMetric({
  label,
  value,
  tone = "default",
}: {
  label: string
  value: ReactNode
  tone?: "default" | "success" | "destructive" | "warning"
}) {
  const toneClass = {
    default: "text-foreground",
    success: "text-success",
    destructive: "text-destructive",
    warning: "text-warning",
  }[tone]

  return (
    <div className="rounded-lg border border-border/60 bg-muted/25 px-3 py-2.5">
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <p className={`mt-1 text-lg font-semibold ${toneClass}`}>{value}</p>
    </div>
  )
}

function RecentActivityCard({
  data,
  loading,
}: {
  data?: DashboardStats
  loading: boolean
}) {
  const total = data?.recent_24h_total ?? 0
  const success = data?.recent_24h_success ?? 0
  const error = data?.recent_24h_error ?? 0
  const successPercent = total > 0 ? Math.round((success / total) * 100) : 0
  const errorPercent = total > 0 ? Math.round((error / total) * 100) : 0
  const quietPercent = Math.max(100 - successPercent - errorPercent, 0)

  return (
    <Card className="border-border/60 shadow-sm">
      <CardHeader className="pb-1">
        <CardTitle className="flex items-center gap-2 text-sm font-medium">
          <Activity className="size-4 text-primary" />
          最近 24 小时
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {loading ? (
          <>
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-10 w-full" />
          </>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
              <ActivityMetric label="请求" value={total} />
              <ActivityMetric label="成功" value={success} tone="success" />
              <ActivityMetric label="异常" value={error} tone="destructive" />
              <ActivityMetric
                label="流式"
                value={data?.recent_24h_stream ?? 0}
                tone="warning"
              />
              <ActivityMetric
                label="平均耗时"
                value={data?.recent_24h_avg_duration ?? "-"}
              />
            </div>

            <div>
              <div className="mb-2 flex items-center justify-between text-[11px] text-muted-foreground">
                <span>成功率 {successPercent}%</span>
                <span>异常率 {errorPercent}%</span>
              </div>
              <div className="flex h-2 overflow-hidden rounded-full bg-muted">
                <div
                  className="bg-success"
                  style={{ width: `${successPercent}%` }}
                />
                <div
                  className="bg-destructive"
                  style={{ width: `${errorPercent}%` }}
                />
                <div
                  className="bg-muted-foreground/15"
                  style={{ width: `${quietPercent}%` }}
                />
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}

function RecentErrorRow({
  item,
  onOpen,
}: {
  item: RecentError
  onOpen: () => void
}) {
  const message = item.error_message || item.upstream_summary || "上游异常"

  return (
    <button
      type="button"
      onClick={onOpen}
      className="grid w-full grid-cols-[auto_1fr_auto] items-center gap-3 rounded-lg px-2 py-2 text-left transition-colors hover:bg-muted/45"
    >
      <div className="flex size-8 items-center justify-center rounded-lg bg-destructive/10 text-destructive">
        <AlertTriangle className="size-4" />
      </div>
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[11px] text-muted-foreground">
            {item.time_str}
          </span>
          <span className="truncate text-xs font-medium">
            {item.method} {item.path}
          </span>
        </div>
        <p className="mt-0.5 truncate text-[11px] text-muted-foreground">
          {item.api_key_name || "-"} · {message}
        </p>
      </div>
      <div className="text-right">
        <div
          className={`text-xs font-semibold ${
            item.status_code >= 400 ? "text-destructive" : "text-warning"
          }`}
        >
          {item.status_code}
        </div>
        <div className="mt-0.5 text-[10px] text-muted-foreground">
          {item.duration_display}
        </div>
      </div>
    </button>
  )
}

function RecentErrorsCard({
  data,
  loading,
}: {
  data?: DashboardStats
  loading: boolean
}) {
  const navigate = useNavigate()
  const recentErrors = data?.recent_errors ?? []

  return (
    <Card className="border-border/60 shadow-sm">
      <CardHeader className="pb-1">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2 text-sm font-medium">
            <AlertTriangle className="size-4 text-destructive" />
            最近异常请求
          </CardTitle>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs"
            onClick={() => navigate("/admin/logs?status=error")}
          >
            全部
            <ArrowRight className="ml-1 size-3" />
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, index) => (
              <Skeleton key={index} className="h-12 w-full" />
            ))}
          </div>
        ) : recentErrors.length > 0 ? (
          <div className="space-y-1">
            {recentErrors.map((item) => (
              <RecentErrorRow
                key={item.request_id}
                item={item}
                onOpen={() => navigate(`/admin/logs/${item.request_id}`)}
              />
            ))}
          </div>
        ) : (
          <div className="rounded-lg border border-border/60 bg-muted/25 px-3 py-8 text-center">
            <CheckCircle2 className="mx-auto size-7 text-success" />
            <p className="mt-2 text-sm font-medium">最近没有异常</p>
            <p className="mt-1 text-xs text-muted-foreground">
              24 小时内未记录错误或上游异常
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function PolicyItem({
  icon,
  label,
  value,
  loading,
}: {
  icon: ReactNode
  label: string
  value: ReactNode
  loading: boolean
}) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-border/60 bg-muted/25 px-3 py-2.5">
      <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-background text-muted-foreground">
        {icon}
      </div>
      <div className="min-w-0">
        <p className="text-[11px] text-muted-foreground">{label}</p>
        {loading ? (
          <Skeleton className="mt-1 h-4 w-20" />
        ) : (
          <p className="mt-0.5 truncate text-sm font-medium">{value}</p>
        )}
      </div>
    </div>
  )
}

function LogPolicyCard({
  data,
  loading,
}: {
  data?: DashboardStats
  loading: boolean
}) {
  return (
    <Card className="border-border/60 shadow-sm">
      <CardHeader className="pb-1">
        <CardTitle className="flex items-center gap-2 text-sm font-medium">
          <Settings2 className="size-4 text-primary" />
          日志策略
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-2">
        <PolicyItem
          icon={<Database className="size-4" />}
          label="保留上限"
          value={`${data?.request_log_retention ?? "-"} 条`}
          loading={loading}
        />
        <PolicyItem
          icon={<FileText className="size-4" />}
          label="正文上限"
          value={data?.request_log_body_limit ?? "-"}
          loading={loading}
        />
        <PolicyItem
          icon={<Activity className="size-4" />}
          label="当前保存"
          value={`${data?.log_count ?? "-"} 条`}
          loading={loading}
        />
        <PolicyItem
          icon={<Clock className="size-4" />}
          label="时区"
          value={data?.timezone ?? "-"}
          loading={loading}
        />
      </CardContent>
    </Card>
  )
}

function QuickActionsCard() {
  const navigate = useNavigate()

  const actions = [
    {
      label: "管理账号池",
      icon: <Pencil className="size-4" />,
      onClick: () => navigate("/admin/token"),
    },
    {
      label: "创建 API Key",
      icon: <Plus className="size-4" />,
      onClick: () => navigate("/admin/keys"),
    },
    {
      label: "查看请求日志",
      icon: <FileText className="size-4" />,
      onClick: () => navigate("/admin/logs"),
    },
    {
      label: "查看异常日志",
      icon: <AlertTriangle className="size-4" />,
      onClick: () => navigate("/admin/logs?status=error"),
    },
  ]

  return (
    <Card className="border-border/60 shadow-sm">
      <CardHeader className="pb-1">
        <CardTitle className="flex items-center gap-2 text-sm font-medium">
          <ArrowRight className="size-4 text-primary" />
          快捷操作
        </CardTitle>
      </CardHeader>
      <CardContent className="grid grid-cols-2 gap-2">
        {actions.map((action) => (
          <Button
            key={action.label}
            variant="outline"
            size="sm"
            className="h-9 justify-start text-xs"
            onClick={action.onClick}
          >
            {action.icon}
            {action.label}
          </Button>
        ))}
      </CardContent>
    </Card>
  )
}

export default function DashboardPage() {
  const { data, loading, error } = usePolling<DashboardStats>(
    api.stats,
    30000,
  )

  return (
    <div className="mx-auto w-full max-w-[1320px] space-y-5">
      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          加载失败：{error}
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          icon={<Clock className="size-4" />}
          title="服务运行时间"
          value={data?.uptime ?? "-"}
          detail="当前进程已持续运行"
          loading={loading}
        />
        <StatCard
          icon={<Key className="size-4" />}
          title="账号池"
          value={
            data ? (
              <div className="flex min-w-0 items-center gap-2">
                <span className="truncate">
                  {data.account_total > 0
                    ? `${data.account_healthy}/${data.account_enabled} 健康`
                    : data.token_status}
                </span>
                <Badge
                  variant={
                    (data.account_total > 0
                      ? data.account_unhealthy === 0
                      : data.token_healthy)
                      ? "default"
                      : "destructive"
                  }
                  className="text-[10px]"
                >
                  {(data.account_total > 0
                    ? data.account_unhealthy === 0
                    : data.token_healthy)
                    ? "正常"
                    : "异常"}
                </Badge>
              </div>
            ) : (
              "-"
            )
          }
          detail={
            data
              ? data.account_total > 0
                ? `总 ${data.account_total} · 占用 ${data.account_in_flight}`
                : `类型：${data.token_type}`
              : undefined
          }
          loading={loading}
        />
        <StatCard
          icon={<Shield className="size-4" />}
          title="API Keys"
          value={data?.key_count ?? "-"}
          detail="可用于 OpenAI 兼容接口"
          loading={loading}
        />
        <StatCard
          icon={<Activity className="size-4" />}
          title="总请求数"
          value={data?.total_requests ?? "-"}
          detail={`${data?.log_count ?? "-"} 条日志已保存`}
          loading={loading}
        />
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-5">
          <RecentActivityCard data={data ?? undefined} loading={loading} />
          <RecentErrorsCard data={data ?? undefined} loading={loading} />
        </div>

        <div className="space-y-5">
          <LogPolicyCard data={data ?? undefined} loading={loading} />
          <QuickActionsCard />
          <Card className="border-border/60 shadow-sm">
            <CardContent className="pt-4">
              <div className="flex items-center gap-3">
                <div className="flex size-9 items-center justify-center rounded-lg bg-warning-muted/35 text-warning">
                  <Radio className="size-4" />
                </div>
                <div>
                  <p className="text-sm font-medium">流式请求</p>
                  <p className="text-xs text-muted-foreground">
                    最近 24 小时记录 {data?.recent_24h_stream ?? "-"} 条
                  </p>
                </div>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
                <div className="rounded-lg bg-success-muted/30 px-3 py-2 text-success">
                  <CheckCircle2 className="mb-1 size-4" />
                  {data?.recent_24h_success ?? "-"} 条正常
                </div>
                <div className="rounded-lg bg-destructive/10 px-3 py-2 text-destructive">
                  <XCircle className="mb-1 size-4" />
                  {data?.recent_24h_error ?? "-"} 条异常
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
