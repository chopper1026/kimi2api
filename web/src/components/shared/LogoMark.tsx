import { cn } from "@/lib/utils"

export function LogoMark({ className }: { className?: string }) {
  return (
    <div
      className={cn("rounded-lg bg-logo-background p-1 shadow-sm", className)}
    >
      <svg viewBox="0 0 64 64" className="size-full">
        <defs>
          <linearGradient
            id="kimi-mark"
            x1="14"
            y1="12"
            x2="50"
            y2="52"
            gradientUnits="userSpaceOnUse"
          >
            <stop offset="0" stopColor="var(--logo-start)" />
            <stop offset="1" stopColor="var(--logo-end)" />
          </linearGradient>
        </defs>
        <path
          d="M20 17v30M23 32 39 18M23 32l17 15"
          fill="none"
          stroke="url(#kimi-mark)"
          strokeWidth="7"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M39 31h10m0 0-4-4m4 4-4 4"
          fill="none"
          stroke="var(--logo-highlight)"
          strokeWidth="4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx="48" cy="44" r="3.5" fill="var(--logo-start)" />
      </svg>
    </div>
  )
}
