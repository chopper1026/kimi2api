import { useState, useEffect, useCallback } from "react"
import { RefreshCw, CheckCircle2, Pencil, ShieldCheck } from "lucide-react"
import { api } from "@/lib/api-client"
import type { TokenInfo, TokenValidation, TokenSaveResult } from "@/types"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Textarea } from "@/components/ui/textarea"
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

export default function TokenPage() {
  const [tokenInfo, setTokenInfo] = useState<TokenInfo | null>(null)
  const [loadingToken, setLoadingToken] = useState(true)
  const [tokenError, setTokenError] = useState<string | null>(null)

  const [editOpen, setEditOpen] = useState(false)
  const [rawToken, setRawToken] = useState("")
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saveSuccess, setSaveSuccess] = useState(false)

  const [refreshing, setRefreshing] = useState(false)
  const [refreshError, setRefreshError] = useState<string | null>(null)
  const [refreshSuccess, setRefreshSuccess] = useState(false)

  const [validating, setValidating] = useState(false)
  const [validationError, setValidationError] = useState<string | null>(null)
  const [validation, setValidation] = useState<TokenValidation | null>(null)

  const loadToken = useCallback(async () => {
    setLoadingToken(true)
    setTokenError(null)
    try {
      const info = await api.getToken()
      setTokenInfo(info)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "加载 Token 失败"
      setTokenError(msg)
    } finally {
      setLoadingToken(false)
    }
  }, [])

  useEffect(() => {
    loadToken()
  }, [loadToken])

  const handleRefresh = async () => {
    setRefreshing(true)
    setRefreshError(null)
    setRefreshSuccess(false)
    try {
      const result: TokenSaveResult = await api.refreshToken()
      if (!result.success) throw new Error(result.error || "刷新失败")
      setTokenInfo(result.token)
      setRefreshSuccess(true)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "刷新失败"
      setRefreshError(msg)
    } finally {
      setRefreshing(false)
    }
  }

  const handleValidate = async () => {
    setValidating(true)
    setValidationError(null)
    try {
      const result = await api.validateToken()
      setValidation(result)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "验证失败"
      setValidationError(msg)
    } finally {
      setValidating(false)
    }
  }

  const handleSave = async () => {
    if (!rawToken.trim()) return
    setSaving(true)
    setSaveError(null)
    setSaveSuccess(false)
    try {
      const result: TokenSaveResult = await api.saveToken(rawToken.trim())
      if (!result.success) throw new Error(result.error || "保存失败")
      setTokenInfo(result.token)
      setSaveSuccess(true)
      setTimeout(() => {
        setEditOpen(false)
        setSaveSuccess(false)
        setRawToken("")
      }, 800)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "保存失败"
      setSaveError(msg)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-5">
      {tokenError && (
        <Alert variant="destructive">
          <AlertDescription>{tokenError}</AlertDescription>
        </Alert>
      )}

      <Card className="border-border/60 shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium">Token 状态</CardTitle>
        </CardHeader>
        <CardContent>
          {loadingToken ? (
            <div className="flex items-center gap-2 text-muted-foreground">
              <LoadingSpinner size={16} />
              <span className="text-sm">加载中...</span>
            </div>
          ) : tokenInfo ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <p className="text-xs text-muted-foreground">Token 类型</p>
                <p className="mt-0.5 text-sm font-medium">{tokenInfo.token_type}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">过期时间</p>
                <p className="mt-0.5 text-sm font-medium">{tokenInfo.token_expires}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Token 预览</p>
                <p className="mt-0.5 font-mono text-xs">{tokenInfo.token_preview}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">状态</p>
                <div className="mt-0.5">
                  <Badge
                    variant={tokenInfo.token_healthy ? "default" : "destructive"}
                    className="text-xs"
                  >
                    {tokenInfo.token_status}
                  </Badge>
                </div>
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">无 Token 信息</p>
          )}
        </CardContent>
      </Card>

      <Card className="border-border/60 shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium">操作</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            <Dialog open={editOpen} onOpenChange={setEditOpen}>
              <DialogTrigger render={<Button variant="outline" size="sm" />}>
                <Pencil className="mr-1.5 h-3.5 w-3.5" />
                编辑 Token
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>编辑 Token</DialogTitle>
                </DialogHeader>
                <div className="space-y-4">
                  {saveSuccess && (
                    <Alert>
                      <AlertDescription>保存成功</AlertDescription>
                    </Alert>
                  )}
                  {saveError && (
                    <Alert variant="destructive">
                      <AlertDescription>{saveError}</AlertDescription>
                    </Alert>
                  )}
                  <Textarea
                    placeholder="粘贴 raw_token..."
                    value={rawToken}
                    onChange={(e) => setRawToken(e.target.value)}
                    rows={4}
                  />
                </div>
                <DialogFooter>
                  <DialogClose render={<Button variant="outline" />}>
                    取消
                  </DialogClose>
                  <Button onClick={handleSave} disabled={saving || !rawToken.trim()}>
                    {saving ? <LoadingSpinner size={16} className="mr-2" /> : null}
                    保存
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>

            <Button variant="outline" size="sm" onClick={handleRefresh} disabled={refreshing}>
              {refreshing ? (
                <LoadingSpinner size={14} className="mr-1.5" />
              ) : (
                <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
              )}
              刷新 Token
            </Button>

            <Button variant="outline" size="sm" onClick={handleValidate} disabled={validating}>
              {validating ? (
                <LoadingSpinner size={14} className="mr-1.5" />
              ) : (
                <ShieldCheck className="mr-1.5 h-3.5 w-3.5" />
              )}
              验证 Token
            </Button>
          </div>

          {refreshSuccess && (
            <Alert className="mt-3">
              <AlertDescription>Token 刷新成功</AlertDescription>
            </Alert>
          )}
          {refreshError && (
            <Alert variant="destructive" className="mt-3">
              <AlertDescription>{refreshError}</AlertDescription>
            </Alert>
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
              验证结果
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <p className="text-xs text-muted-foreground">有效状态</p>
              <div className="mt-0.5">
                <Badge variant={validation.valid ? "default" : "destructive"}>
                  {validation.valid ? "有效" : "无效"}
                </Badge>
              </div>
            </div>
            {validation.subscription &&
              Object.keys(validation.subscription).length > 0 && (
                <div>
                  <p className="text-xs text-muted-foreground mb-1">订阅信息</p>
                  <pre className="rounded-lg bg-muted/60 p-3 text-xs overflow-auto max-h-80">
                    {JSON.stringify(validation.subscription, null, 2)}
                  </pre>
                </div>
              )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
