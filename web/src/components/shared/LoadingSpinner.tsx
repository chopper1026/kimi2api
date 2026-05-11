import { cn } from "@/lib/utils"

interface LoadingSpinnerProps {
  size?: number
  className?: string
}

export function LoadingSpinner({ size = 20, className }: LoadingSpinnerProps) {
  return (
    <div
      className={cn(
        "inline-block rounded-full border-2 border-muted-foreground/30 border-t-foreground animate-spin",
        className,
      )}
      style={{ width: size, height: size }}
    />
  )
}
