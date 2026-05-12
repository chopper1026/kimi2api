import type { ComponentProps } from "react"

import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"

function PageSkeleton({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-loading-skeleton="page"
      className={cn("space-y-4", className)}
      {...props}
    />
  )
}

function CardSkeleton({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-loading-skeleton="card"
      className={cn(
        "rounded-lg border border-border/60 bg-card p-4 shadow-sm",
        className,
      )}
      {...props}
    />
  )
}

function MetricGridSkeleton({
  count = 4,
  className,
}: {
  count?: number
  className?: string
}) {
  return (
    <div
      data-loading-skeleton="metric-grid"
      className={cn("grid grid-cols-2 gap-3 md:grid-cols-4", className)}
    >
      {Array.from({ length: count }).map((_, index) => (
        <CardSkeleton key={index} className="space-y-3">
          <Skeleton className="h-3 w-16" />
          <Skeleton className="h-7 w-20" />
        </CardSkeleton>
      ))}
    </div>
  )
}

function TableSkeleton({
  rows = 5,
  columns = 6,
  className,
}: {
  rows?: number
  columns?: number
  className?: string
}) {
  return (
    <div
      data-loading-skeleton="table"
      className={cn(
        "overflow-hidden rounded-lg border border-border/60 bg-card shadow-sm",
        className,
      )}
    >
      <div
        className="grid gap-3 border-b border-border/60 bg-muted/20 px-3 py-3"
        style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
      >
        {Array.from({ length: columns }).map((_, index) => (
          <Skeleton key={index} className="h-3 w-14" />
        ))}
      </div>
      <div className="divide-y divide-border/60">
        {Array.from({ length: rows }).map((_, rowIndex) => (
          <div
            key={rowIndex}
            className="grid gap-3 px-3 py-3"
            style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
          >
            {Array.from({ length: columns }).map((_, columnIndex) => (
              <Skeleton
                key={columnIndex}
                className={cn(
                  "h-4",
                  columnIndex % 3 === 0
                    ? "w-16"
                    : columnIndex % 3 === 1
                      ? "w-24"
                      : "w-12",
                )}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

function MobileListSkeleton({
  items = 3,
  className,
}: {
  items?: number
  className?: string
}) {
  return (
    <PageSkeleton data-loading-skeleton="mobile-list" className={className}>
      {Array.from({ length: items }).map((_, index) => (
        <CardSkeleton key={index} className="space-y-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1 space-y-2">
              <Skeleton className="h-3 w-20" />
              <Skeleton className="h-4 w-4/5" />
              <Skeleton className="h-3 w-32" />
            </div>
            <Skeleton className="h-7 w-10" />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        </CardSkeleton>
      ))}
    </PageSkeleton>
  )
}

function DetailSkeleton({ className }: { className?: string }) {
  return (
    <PageSkeleton data-loading-skeleton="detail" className={cn("space-y-5", className)}>
      <div className="flex items-center gap-3">
        <Skeleton className="size-8 rounded-lg" />
        <Skeleton className="h-4 w-64 max-w-[70vw]" />
      </div>
      <MetricGridSkeleton />
      <CardSkeleton className="space-y-3">
        <Skeleton className="h-4 w-20" />
        <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
          {Array.from({ length: 6 }).map((_, index) => (
            <Skeleton key={index} className="h-4 w-full" />
          ))}
        </div>
      </CardSkeleton>
      <CardSkeleton className="space-y-3">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-40 w-full" />
      </CardSkeleton>
    </PageSkeleton>
  )
}

function TokenStatusSkeleton({ className }: { className?: string }) {
  return (
    <div
      data-loading-skeleton="token-status"
      className={cn("grid grid-cols-1 gap-4 md:grid-cols-2", className)}
    >
      {Array.from({ length: 4 }).map((_, index) => (
        <div key={index} className="space-y-2">
          <Skeleton className="h-3 w-20" />
          <Skeleton className="h-4 w-28" />
        </div>
      ))}
    </div>
  )
}

export {
  PageSkeleton,
  CardSkeleton,
  MetricGridSkeleton,
  TableSkeleton,
  MobileListSkeleton,
  DetailSkeleton,
  TokenStatusSkeleton,
}
