import { useState, useEffect, useCallback } from "react"
import {
  CheckCircle2,
  Pencil,
  Plus,
  RefreshCw,
  ShieldCheck,
  Trash2,
} from "lucide-react"

import { api } from "@/lib/api-client"
import type {
  KimiAccountInfo,
  KimiAccountsSummary,
  KimiAccountSaveResult,
  TokenValidation,
} from "@/types"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Textarea } from "@/components/ui/textarea"
import { Input } from "@/components/ui/input"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog"
import { LoadingSpinner } from "@/components/shared/LoadingSpinner"
import { TokenStatusSkeleton } from "@/components/shared/PageSkeletons"

interface AccountFormState {
  id?: string
  name: string
  rawToken: string
  enabled: boolean
  maxConcurrency: string
  minIntervalSeconds: string
}

const emptySummary: KimiAccountsSummary = {
  total: 0,
  enabled: 0,
  healthy: 0,
  unhealthy: 0,
  in_flight: 0,
}

function blankForm(): AccountFormState {
  return {
    name: "",
    rawToken: "",
    enabled: true,
    maxConcurrency: "2",
    minIntervalSeconds: "0.5",
  }
}

function formFromAccount(account: KimiAccountInfo): AccountFormState {
  return {
    id: account.id,
    name: account.name,
    rawToken: "",
    enabled: account.enabled,
    maxConcurrency: String(account.max_concurrency),
    minIntervalSeconds: String(account.min_interval_seconds),
  }
}

function metric(label: string, value: number) {
  return (
    <div className="rounded-lg border border-border/60 bg-muted/25 px-3 py-2">
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-semibold">{value}</p>
    </div>
  )
}

function AccountDetail({
  label,
  value,
  mono = false,
}: {
  label: string
  value: string | number
  mono?: boolean
}) {
  return (
    <div className="min-w-0 rounded-lg bg-muted/35 px-3 py-2.5">
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <p
        className={`mt-1 truncate font-medium ${
          mono ? "font-mono text-xs" : "text-sm"
        }`}
        title={String(value)}
      >
        {value}
      </p>
    </div>
  )
}

export default function TokenPage() {
  const [accounts, setAccounts] = useState<KimiAccountInfo[]>([])
  const [summary, setSummary] = useState<KimiAccountsSummary>(emptySummary)
  const [loadingToken, setLoadingToken] = useState(true)
  const [tokenError, setTokenError] = useState<string | null>(null)

  const [editOpen, setEditOpen] = useState(false)
  const [form, setForm] = useState<AccountFormState>(blankForm)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  const [busyAccount, setBusyAccount] = useState<string | null>(null)
  const [refreshError, setRefreshError] = useState<string | null>(null)
  const [refreshSuccess, setRefreshSuccess] = useState<string | null>(null)

  const [validating, setValidating] = useState<string | null>(null)
  const [validationError, setValidationError] = useState<string | null>(null)
  const [validation, setValidation] = useState<{
    account: string
    result: TokenValidation
  } | null>(null)

  const applyAccounts = (result: {
    accounts: KimiAccountInfo[]
    summary: KimiAccountsSummary
  }) => {
    setAccounts(result.accounts)
    setSummary(result.summary)
  }

  const loadToken = useCallback(async () => {
    setLoadingToken(true)
    setTokenError(null)
    try {
      const info = await api.getTokens()
      applyAccounts(info)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "加载账号池失败"
      setTokenError(msg)
    } finally {
      setLoadingToken(false)
    }
  }, [])

  useEffect(() => {
    loadToken()
  }, [loadToken])

  const openCreate = () => {
    setForm(blankForm())
    setSaveError(null)
    setEditOpen(true)
  }

  const openEdit = (account: KimiAccountInfo) => {
    setForm(formFromAccount(account))
    setSaveError(null)
    setEditOpen(true)
  }

  const handleSave = async () => {
    if (!form.id && !form.rawToken.trim()) return
    setSaving(true)
    setSaveError(null)
    try {
      const payload = {
        name: form.name.trim(),
        enabled: form.enabled,
        max_concurrency: Number(form.maxConcurrency) || 1,
        min_interval_seconds: Number(form.minIntervalSeconds) || 0,
      }
      const result: KimiAccountSaveResult = form.id
        ? await api.updateTokenAccount(form.id, {
            ...payload,
            raw_token: form.rawToken.trim() || undefined,
          })
        : await api.createTokenAccount({
            ...payload,
            raw_token: form.rawToken.trim(),
          })
      if (!result.success) throw new Error(result.error || "保存失败")
      applyAccounts(result)
      setEditOpen(false)
      setForm(blankForm())
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "保存失败"
      setSaveError(msg)
    } finally {
      setSaving(false)
    }
  }

  const handleRefresh = async (account: KimiAccountInfo) => {
    setBusyAccount(account.id)
    setRefreshError(null)
    setRefreshSuccess(null)
    try {
      const result = await api.refreshTokenAccount(account.id)
      if (!result.success) throw new Error(result.error || "刷新失败")
      applyAccounts(result)
      setRefreshSuccess(`${account.name} 刷新成功`)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "刷新失败"
      setRefreshError(msg)
    } finally {
      setBusyAccount(null)
    }
  }

  const handleValidate = async (account: KimiAccountInfo) => {
    setValidating(account.id)
    setValidationError(null)
    try {
      const result = await api.validateTokenAccount(account.id)
      setValidation({ account: account.name, result })
      await loadToken()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "验证失败"
      setValidationError(msg)
    } finally {
      setValidating(null)
    }
  }

  const handleDelete = async (account: KimiAccountInfo) => {
    setBusyAccount(account.id)
    setRefreshError(null)
    try {
      const result = await api.deleteTokenAccount(account.id)
      if (!result.success) throw new Error(result.error || "删除失败")
      applyAccounts(result)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "删除失败"
      setRefreshError(msg)
    } finally {
      setBusyAccount(null)
    }
  }

  return (
    <div className="mx-auto w-full max-w-[1320px] space-y-5">
      {tokenError && (
        <Alert variant="destructive">
          <AlertDescription>{tokenError}</AlertDescription>
        </Alert>
      )}

      <Card className="border-border/60 shadow-sm">
        <CardHeader className="pb-3">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <CardTitle className="text-sm font-medium">账号池</CardTitle>
            <Dialog open={editOpen} onOpenChange={setEditOpen}>
              <DialogTrigger
                render={
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-10 w-full sm:h-7 sm:w-auto"
                    onClick={openCreate}
                  />
                }
              >
                <Plus className="mr-1.5 h-3.5 w-3.5" />
                新增账号
              </DialogTrigger>
              <DialogContent className="sm:max-w-md">
                <DialogHeader>
                  <DialogTitle>{form.id ? "编辑账号" : "新增账号"}</DialogTitle>
                </DialogHeader>
                <div className="space-y-3">
                  {saveError && (
                    <Alert variant="destructive">
                      <AlertDescription>{saveError}</AlertDescription>
                    </Alert>
                  )}
                  <div className="grid gap-2">
                    <label className="text-xs text-muted-foreground">名称</label>
                    <Input
                      value={form.name}
                      onChange={(event) =>
                        setForm((current) => ({
                          ...current,
                          name: event.target.value,
                        }))
                      }
                      placeholder="Kimi 账号名称"
                      className="h-10 md:h-8"
                    />
                  </div>
                  <div className="grid gap-2">
                    <label className="text-xs text-muted-foreground">
                      Raw Token
                    </label>
                    <Textarea
                      placeholder={form.id ? "留空则不修改 token" : "粘贴 raw_token..."}
                      value={form.rawToken}
                      onChange={(event) =>
                        setForm((current) => ({
                          ...current,
                          rawToken: event.target.value,
                        }))
                      }
                      rows={4}
                    />
                  </div>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <div className="grid gap-2">
                      <label className="text-xs text-muted-foreground">
                        并发上限
                      </label>
                      <Input
                        type="number"
                        min={1}
                        value={form.maxConcurrency}
                        onChange={(event) =>
                          setForm((current) => ({
                            ...current,
                            maxConcurrency: event.target.value,
                          }))
                        }
                        className="h-10 md:h-8"
                      />
                    </div>
                    <div className="grid gap-2">
                      <label className="text-xs text-muted-foreground">
                        最小间隔（秒）
                      </label>
                      <Input
                        type="number"
                        min={0}
                        step="0.1"
                        value={form.minIntervalSeconds}
                        onChange={(event) =>
                          setForm((current) => ({
                            ...current,
                            minIntervalSeconds: event.target.value,
                          }))
                        }
                        className="h-10 md:h-8"
                      />
                    </div>
                  </div>
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={form.enabled}
                      onChange={(event) =>
                        setForm((current) => ({
                          ...current,
                          enabled: event.target.checked,
                        }))
                      }
                      className="size-4 accent-primary"
                    />
                    启用账号
                  </label>
                </div>
                <DialogFooter>
                  <DialogClose render={<Button variant="outline" />}>
                    取消
                  </DialogClose>
                  <Button
                    onClick={handleSave}
                    disabled={saving || (!form.id && !form.rawToken.trim())}
                  >
                    {saving ? <LoadingSpinner size={16} className="mr-2" /> : null}
                    保存
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {loadingToken ? (
            <TokenStatusSkeleton />
          ) : (
            <>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
                {metric("总账号", summary.total)}
                {metric("启用", summary.enabled)}
                {metric("健康", summary.healthy)}
                {metric("异常", summary.unhealthy)}
                {metric("占用", summary.in_flight)}
              </div>

              {refreshSuccess && (
                <Alert>
                  <AlertDescription>{refreshSuccess}</AlertDescription>
                </Alert>
              )}
              {refreshError && (
                <Alert variant="destructive">
                  <AlertDescription>{refreshError}</AlertDescription>
                </Alert>
              )}

              <div className="grid gap-3">
                {accounts.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-border px-4 py-10 text-center text-sm text-muted-foreground">
                    暂无 Kimi 账号
                  </div>
                ) : (
                  accounts.map((account) => (
                    <div
                      key={account.id}
                      className="rounded-lg border border-border/60 bg-card p-4 shadow-sm"
                    >
                      <div className="flex flex-col gap-4">
                        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                          <div className="flex flex-wrap items-center gap-2">
                            <h3 className="min-w-0 truncate text-sm font-semibold">
                              {account.name}
                            </h3>
                            <Badge
                              variant={
                                account.token_healthy ? "default" : "destructive"
                              }
                              className="text-[10px]"
                            >
                              {account.token_status}
                            </Badge>
                            {!account.enabled && (
                              <Badge variant="secondary" className="text-[10px]">
                                已禁用
                              </Badge>
                            )}
                          </div>
                        </div>

                        <div className="grid grid-cols-2 gap-2 lg:grid-cols-5">
                          <AccountDetail label="类型" value={account.token_type} />
                          <AccountDetail
                            label="过期"
                            value={account.token_expires}
                          />
                          <AccountDetail
                            label="Token"
                            value={account.token_preview}
                            mono
                          />
                          <AccountDetail
                            label="并发"
                            value={`${account.in_flight}/${account.max_concurrency}`}
                          />
                          <AccountDetail
                            label="间隔"
                            value={`${account.min_interval_seconds}s`}
                          />
                        </div>

                        <div
                          data-token-actions
                          className="grid grid-cols-2 gap-2 border-t border-border/60 pt-3 sm:flex sm:flex-wrap sm:justify-end"
                        >
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => openEdit(account)}
                            className="h-10 w-full whitespace-nowrap sm:h-7 sm:w-auto"
                          >
                            <Pencil className="mr-1.5 h-3.5 w-3.5" />
                            编辑
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleRefresh(account)}
                            disabled={busyAccount === account.id}
                            className="h-10 w-full whitespace-nowrap sm:h-7 sm:w-auto"
                          >
                            {busyAccount === account.id ? (
                              <LoadingSpinner size={14} className="mr-1.5" />
                            ) : (
                              <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
                            )}
                            刷新
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleValidate(account)}
                            disabled={validating === account.id}
                            className="h-10 w-full whitespace-nowrap sm:h-7 sm:w-auto"
                          >
                            {validating === account.id ? (
                              <LoadingSpinner size={14} className="mr-1.5" />
                            ) : (
                              <ShieldCheck className="mr-1.5 h-3.5 w-3.5" />
                            )}
                            验证
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleDelete(account)}
                            disabled={busyAccount === account.id}
                            className="h-10 w-full whitespace-nowrap text-destructive hover:text-destructive sm:h-7 sm:w-auto"
                          >
                            <Trash2 className="mr-1.5 h-3.5 w-3.5" />
                            删除
                          </Button>
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {validationError && (
        <Alert variant="destructive">
          <AlertDescription>{validationError}</AlertDescription>
        </Alert>
      )}

      {validation && (
        <Card className="border-border/60 shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm font-medium">
              <CheckCircle2 className="h-4 w-4" />
              验证结果 · {validation.account}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <p className="text-xs text-muted-foreground">有效状态</p>
              <div className="mt-0.5">
                <Badge variant={validation.result.valid ? "default" : "destructive"}>
                  {validation.result.valid ? "有效" : "无效"}
                </Badge>
              </div>
            </div>
            {validation.result.subscription &&
              Object.keys(validation.result.subscription).length > 0 && (
                <div>
                  <p className="mb-1 text-xs text-muted-foreground">订阅信息</p>
                  <pre className="max-h-80 overflow-auto rounded-lg bg-muted/60 p-3 text-xs">
                    {JSON.stringify(validation.result.subscription, null, 2)}
                  </pre>
                </div>
              )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
