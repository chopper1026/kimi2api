import { Clock, Key, Shield, Activity } from "lucide-react"
import { usePolling } from "@/hooks/use-polling"
import { api } from "@/lib/api-client"
import type { DashboardStats } from "@/types"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"

interface StatCardProps {
  icon: React.ReactNode
  title: string
  value: React.ReactNode
  loading: boolean
}

function StatCard({ icon, title, value, loading }: StatCardProps) {
  return (
    <Card className="border-border/60 shadow-sm">
      <CardContent className="pt-5">
        <div className="flex items-center justify-between">
          <div
            className="flex size-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
            {icon}
          </div>
        </div>
        <div className="mt-3">
          {loading ? (
            <Skeleton className="h-7 w-20" />
          ) : (
            <div className="text-2xl font-bold tracking-tight">{value}</div>
          )}
        </div>
        <p className="mt-1 text-xs text-muted-foreground">{title}</p>
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
    <div className="space-y-6">
      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          加载失败：{error}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          icon={<Clock className="size-4" />}
          title="服务运行时间"
          value={data?.uptime ?? "-"}
          loading={loading}
        />
        <StatCard
          icon={<Key className="size-4" />}
          title="Token 状态"
          value={
            data ? (
              <div className="flex items-center gap-2">
                <span className="text-2xl font-bold">{data.token_status}</span>
                <Badge
                  variant={data.token_healthy ? "default" : "destructive"}
                  className="text-[10px]"
                >
                  {data.token_healthy ? "正常" : "异常"}
                </Badge>
              </div>
            ) : (
              "-"
            )
          }
          loading={loading}
        />
        <StatCard
          icon={<Shield className="size-4" />}
          title="API Keys 数量"
          value={data?.key_count ?? "-"}
          loading={loading}
        />
        <StatCard
          icon={<Activity className="size-4" />}
          title="总请求数"
          value={data?.total_requests ?? "-"}
          loading={loading}
        />
      </div>
    </div>
  )
}
