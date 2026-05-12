import { useState, useEffect, useCallback } from "react"
import { api, ApiClientError } from "@/lib/api-client"
import type { KeyItem } from "@/types"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table"
import { CopyButton } from "@/components/shared/CopyButton"
import {
  MobileListSkeleton,
  TableSkeleton,
} from "@/components/shared/PageSkeletons"
import { PlusIcon } from "lucide-react"

function KeyMobileCard({
  item,
  onDelete,
}: {
  item: KeyItem
  onDelete: () => void
}) {
  return (
    <div className="rounded-lg border border-border/60 bg-card p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Key className="size-4 shrink-0 text-muted-foreground" />
            <p className="truncate text-sm font-medium">{item.name || "-"}</p>
          </div>
          <code className="mt-2 block truncate text-xs text-muted-foreground">
            {item.key_preview}
          </code>
        </div>
        <CopyButton text={item.key} className="size-9 shrink-0" />
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
        <div className="rounded-lg bg-muted/35 px-3 py-2">
          <p className="text-muted-foreground">创建时间</p>
          <p className="mt-1 font-medium">{item.created_at_str}</p>
        </div>
        <div className="rounded-lg bg-muted/35 px-3 py-2">
          <p className="text-muted-foreground">上次使用</p>
          <p className="mt-1 font-medium">{item.last_used_str}</p>
        </div>
      </div>

      <div className="mt-4 flex items-center justify-between gap-3 border-t border-border/60 pt-3">
        <span className="text-xs text-muted-foreground">
          请求数 <span className="font-medium text-foreground">{item.request_count}</span>
        </span>
        <Button
          variant="destructive"
          size="sm"
          onClick={onDelete}
          className="h-9 px-3 text-xs"
        >
          删除
        </Button>
      </div>
    </div>
  )
}

export default function KeysPage() {
  const [keys, setKeys] = useState<KeyItem[]>([])
  const [loading, setLoading] = useState(true)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [keyName, setKeyName] = useState("")
  const [creating, setCreating] = useState(false)
  const [newKey, setNewKey] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const fetchKeys = useCallback(async () => {
    try {
      setLoading(true)
      const data = await api.getKeys()
      setKeys(data.keys)
    } catch {
      setError("加载 Key 列表失败")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchKeys()
  }, [fetchKeys])

  const handleCreate = async () => {
    try {
      setCreating(true)
      setError(null)
      const data = await api.createKey(keyName.trim() || undefined)
      setKeys(data.keys)
      if (data.new_key) {
        setNewKey(data.new_key)
      }
      setKeyName("")
      setDialogOpen(false)
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.message)
      } else {
        setError("创建 Key 失败")
      }
    } finally {
      setCreating(false)
    }
  }

  const handleDelete = async (key: string) => {
    if (!window.confirm("确认删除该 Key？此操作不可撤销。")) return
    try {
      setError(null)
      const data = await api.deleteKey(key)
      setKeys(data.keys)
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.message)
      } else {
        setError("删除 Key 失败")
      }
    }
  }

  return (
    <div className="mx-auto w-full max-w-[1320px] space-y-5">
      <div className="flex items-center justify-between">
        <div />
        <Button
          size="sm"
          className="h-10 w-full md:h-7 md:w-auto"
          onClick={() => setDialogOpen(true)}
        >
          <PlusIcon className="mr-1.5 size-3.5" />
          创建 Key
        </Button>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {newKey && (
        <div className="rounded-lg border border-success/35 bg-success-muted/25 px-4 py-3">
          <p className="mb-1.5 text-xs font-medium text-success">
            Key 创建成功，请立即保存（仅显示一次）：
          </p>
          <div className="flex flex-col items-stretch gap-2 md:flex-row md:items-center">
            <code className="rounded-md bg-card px-3 py-2 font-mono text-xs break-all border border-border/60">
              {newKey}
            </code>
            <CopyButton text={newKey} />
          </div>
        </div>
      )}

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>创建新 Key</DialogTitle>
          </DialogHeader>
          <div className="py-2">
            <label className="mb-1.5 block text-xs text-muted-foreground">
              名称（可选）
            </label>
            <Input
              placeholder="输入 Key 名称"
              value={keyName}
              onChange={(e) => setKeyName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleCreate()
              }}
            />
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDialogOpen(false)}
              disabled={creating}
            >
              取消
            </Button>
            <Button onClick={handleCreate} disabled={creating}>
              {creating ? "创建中..." : "创建"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {loading ? (
        <>
          <MobileListSkeleton items={3} className="md:hidden" />
          <TableSkeleton rows={3} columns={6} className="hidden md:block" />
        </>
      ) : keys.length === 0 ? (
        <div className="rounded-lg border border-border/60 bg-card py-16 text-center shadow-sm">
          <Key className="mx-auto size-8 text-muted-foreground/30" />
          <p className="mt-3 text-sm text-muted-foreground">
            暂无 API Key
          </p>
          <p className="mt-1 text-xs text-muted-foreground/60">
            点击上方按钮创建
          </p>
        </div>
      ) : (
        <>
          <div className="space-y-3 md:hidden">
            {keys.map((item) => (
              <KeyMobileCard
                key={item.key}
                item={item}
                onDelete={() => handleDelete(item.key)}
              />
            ))}
          </div>

          <div className="hidden md:block rounded-lg border border-border/60 bg-card shadow-sm overflow-hidden">
            <Table className="min-w-[860px] table-fixed">
              <colgroup>
                <col className="w-[18%]" />
                <col className="w-[30%]" />
                <col className="w-[18%]" />
                <col className="w-[18%]" />
                <col className="w-[8%]" />
                <col className="w-24" />
              </colgroup>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="text-xs">名称</TableHead>
                  <TableHead className="text-xs">Key</TableHead>
                  <TableHead className="text-xs">创建时间</TableHead>
                  <TableHead className="text-xs">上次使用</TableHead>
                  <TableHead className="text-center text-xs">请求数</TableHead>
                  <TableHead className="text-left text-xs">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {keys.map((item) => (
                  <TableRow key={item.key}>
                    <TableCell className="truncate text-sm font-medium">
                      {item.name || "-"}
                    </TableCell>
                    <TableCell>
                      <div className="flex min-w-0 items-center gap-1.5">
                        <code className="truncate text-xs text-muted-foreground">
                          {item.key_preview}
                        </code>
                        <CopyButton text={item.key} />
                      </div>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {item.created_at_str}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {item.last_used_str}
                    </TableCell>
                    <TableCell className="text-center text-xs">
                      {item.request_count}
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="destructive"
                        size="xs"
                        onClick={() => handleDelete(item.key)}
                        className="h-7 px-2.5 text-[11px]"
                      >
                        删除
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </>
      )}
    </div>
  )
}

function Key({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <circle cx="7.5" cy="15.5" r="5.5" />
      <path d="m21 2-9.6 9.6" />
      <path d="m15.5 7.5 3 3L22 7l-3-3" />
    </svg>
  )
}
