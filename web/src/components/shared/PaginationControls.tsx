import {
  ChevronLeftIcon,
  ChevronRightIcon,
  ChevronsLeftIcon,
  ChevronsRightIcon,
} from "lucide-react"

import { Button } from "@/components/ui/button"

interface PaginationControlsProps {
  page: number
  pageCount: number
  total: number
  startIndex: number
  endIndex: number
  onPageChange: (page: number) => void
}

export function PaginationControls({
  page,
  pageCount,
  total,
  startIndex,
  endIndex,
  onPageChange,
}: PaginationControlsProps) {
  const hasPrev = page > 1
  const hasNext = page < pageCount

  return (
    <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
      <p className="text-xs text-muted-foreground">
        第 {startIndex}-{endIndex} 条，共 {total} 条
      </p>
      <div className="flex items-center justify-between gap-1 md:justify-end">
        <Button
          variant="outline"
          size="icon-xs"
          disabled={!hasPrev}
          onClick={() => onPageChange(1)}
          title="首页"
        >
          <ChevronsLeftIcon className="size-3.5" />
        </Button>
        <Button
          variant="outline"
          size="icon-xs"
          disabled={!hasPrev}
          onClick={() => onPageChange(page - 1)}
          title="上一页"
        >
          <ChevronLeftIcon className="size-3.5" />
        </Button>
        <span className="px-2 text-xs text-muted-foreground">
          {page} / {pageCount}
        </span>
        <Button
          variant="outline"
          size="icon-xs"
          disabled={!hasNext}
          onClick={() => onPageChange(page + 1)}
          title="下一页"
        >
          <ChevronRightIcon className="size-3.5" />
        </Button>
        <Button
          variant="outline"
          size="icon-xs"
          disabled={!hasNext}
          onClick={() => onPageChange(pageCount)}
          title="末页"
        >
          <ChevronsRightIcon className="size-3.5" />
        </Button>
      </div>
    </div>
  )
}
