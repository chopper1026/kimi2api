import { useState } from "react"
import { ChevronRightIcon } from "lucide-react"

import { cn } from "@/lib/utils"

type JsonNodeProps = {
  value: unknown
  label?: string
  labelKind?: "key" | "index"
  depth?: number
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
}

function JsonLabel({
  label,
  kind = "key",
}: {
  label?: string
  kind?: "key" | "index"
}) {
  if (label === undefined) return null

  if (kind === "index") {
    return (
      <>
        <span className="text-muted-foreground">[{label}]</span>
        <span className="text-muted-foreground">:</span>
      </>
    )
  }

  return (
    <>
      <span className="text-json-key">
        {JSON.stringify(label)}
      </span>
      <span className="text-muted-foreground">:</span>
    </>
  )
}

function JsonPrimitive({ value }: { value: unknown }) {
  if (value === null) {
    return <span className="text-muted-foreground italic">null</span>
  }

  if (typeof value === "string") {
    return (
      <span className="break-all text-json-string">
        {JSON.stringify(value)}
      </span>
    )
  }

  if (typeof value === "number") {
    return <span className="text-json-number">{value}</span>
  }

  if (typeof value === "boolean") {
    return (
      <span className="text-json-boolean">
        {String(value)}
      </span>
    )
  }

  return <span>{String(value)}</span>
}

function JsonNode({
  value,
  label,
  labelKind = "key",
  depth = 0,
}: JsonNodeProps) {
  const isArray = Array.isArray(value)
  const isObject = isPlainObject(value)
  const isExpandable = isArray || isObject
  const [expanded, setExpanded] = useState(depth < 2)

  if (!isExpandable) {
    return (
      <div className="flex items-start gap-1 py-0.5">
        <JsonLabel label={label} kind={labelKind} />
        <JsonPrimitive value={value} />
      </div>
    )
  }

  const entries = isArray
    ? value.map((item, index) => [String(index), item] as const)
    : Object.entries(value)
  const openChar = isArray ? "[" : "{"
  const closeChar = isArray ? "]" : "}"
  const summary = isArray
    ? `${entries.length} items`
    : `${entries.length} keys`

  if (entries.length === 0) {
    return (
      <div className="flex items-start gap-1 py-0.5">
        <JsonLabel label={label} kind={labelKind} />
        <span className="text-muted-foreground">
          {openChar}
          {closeChar}
        </span>
      </div>
    )
  }

  return (
    <div className="py-0.5">
      <div className="flex items-center gap-1">
        <button
          type="button"
          className="inline-flex size-4 shrink-0 items-center justify-center rounded text-muted-foreground hover:bg-background hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/40 focus-visible:outline-none"
          aria-label={expanded ? "收起 JSON 节点" : "展开 JSON 节点"}
          onClick={() => setExpanded((value) => !value)}
        >
          <ChevronRightIcon
            className={cn(
              "size-3 transition-transform",
              expanded && "rotate-90",
            )}
          />
        </button>
        <JsonLabel label={label} kind={labelKind} />
        <span className="text-muted-foreground">{openChar}</span>
        {!expanded && (
          <>
            <span className="text-muted-foreground/70">...</span>
            <span className="rounded bg-background px-1 text-[10px] text-muted-foreground">
              {summary}
            </span>
            <span className="text-muted-foreground">{closeChar}</span>
          </>
        )}
      </div>
      {expanded && (
        <>
          <div className="ml-4 border-l border-border/70 pl-3">
            {entries.map(([entryLabel, entryValue]) => (
              <JsonNode
                key={entryLabel}
                value={entryValue}
                label={entryLabel}
                labelKind={isArray ? "index" : "key"}
                depth={depth + 1}
              />
            ))}
          </div>
          <div className="ml-4 text-muted-foreground">{closeChar}</div>
        </>
      )}
    </div>
  )
}

export function JsonTreeView({
  value,
  label,
}: {
  value: unknown
  label?: string
}) {
  return (
    <div className="font-mono text-[11px] leading-5">
      <JsonNode value={value} label={label} />
    </div>
  )
}
