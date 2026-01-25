import type { Interrupt } from "@langchain/langgraph-sdk"

import { Button } from "@/components/ui/button"
import { getLoginUrl } from "@/lib/use-auth"

interface GoogleAuthInterruptValue {
  type: string
  message: string
  action: string
}

interface GoogleAuthHandlerProps {
  interrupt: Interrupt | undefined | null
  onFinish: () => void
}

function isGoogleAuthInterrupt(value: unknown): value is GoogleAuthInterruptValue {
  if (!value || typeof value !== "object") return false
  const v = value as Record<string, unknown>
  return v.type === "google_auth_required"
}

export function GoogleAuthHandler({
  interrupt,
  onFinish,
}: GoogleAuthHandlerProps) {
  if (!interrupt || !isGoogleAuthInterrupt(interrupt.value)) {
    return null
  }

  const handleAuthorize = () => {
    const returnTo = window.location.pathname + window.location.search
    const loginUrl = `/api/auth/login?returnTo=${encodeURIComponent(returnTo)}`

    const popup = window.open(loginUrl, "google-auth", "width=500,height=600")

    if (popup) {
      const checkClosed = setInterval(() => {
        if (popup.closed) {
          clearInterval(checkClosed)
          onFinish()
        }
      }, 500)
    } else {
      window.location.href = loginUrl
    }
  }

  return (
    <div className="flex flex-col gap-4 p-4 border rounded-lg bg-muted/50">
      <div className="flex flex-col gap-2">
        <h3 className="font-semibold">Authorization Required</h3>
        <p className="text-sm text-muted-foreground">
          {interrupt.value.message}
        </p>
      </div>
      <Button onClick={handleAuthorize} className="w-fit">
        Connect Google Account
      </Button>
    </div>
  )
}
