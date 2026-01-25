import { Button } from "@/components/ui/button"
import useAuth, { getLoginUrl } from "@/lib/use-auth"
import { LogIn, Mail, Calendar } from "lucide-react"
import { ChatWindow } from "@/components/chat-window"

function InfoCard() {
  return (
    <div className="flex flex-col items-center justify-center h-full px-4">
      <div className="max-w-md w-full space-y-6 text-center">
        <div className="flex justify-center gap-4 mb-4">
          <div className="p-3 rounded-full bg-primary/10">
            <Mail className="w-6 h-6 text-primary" />
          </div>
          <div className="p-3 rounded-full bg-primary/10">
            <Calendar className="w-6 h-6 text-primary" />
          </div>
        </div>
        <h2 className="text-xl font-semibold text-foreground">
          Welcome to Inbox Pilot
        </h2>
        <p className="text-muted-foreground">
          Your AI-powered email and calendar assistant. I can help you manage
          your inbox, schedule meetings, and stay organized.
        </p>
        <div className="border border-border rounded-lg p-4 bg-card text-left space-y-2">
          <p className="text-sm font-medium text-foreground">Try asking:</p>
          <ul className="text-sm text-muted-foreground space-y-1">
            <li>- What emails do I have?</li>
            <li>- What's on my calendar today?</li>
            <li>- Schedule a meeting for tomorrow at 2pm</li>
            <li>- Draft a reply to the latest email</li>
          </ul>
        </div>
      </div>
    </div>
  )
}

export default function ChatPage() {
  const { user, isLoading } = useAuth()

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-pulse text-muted-foreground">Loading...</div>
      </div>
    )
  }

  if (!user) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[50vh] my-auto gap-6 px-4">
        <div className="text-center space-y-2">
          <h2 className="text-2xl font-semibold text-foreground">
            Welcome to Inbox Pilot
          </h2>
          <p className="text-muted-foreground">
            Sign in to start managing your email and calendar with AI
          </p>
        </div>
        <Button asChild variant="default" size="lg">
          <a href={getLoginUrl()} className="flex items-center gap-2">
            <LogIn className="w-4 h-4" />
            <span>Login with Google</span>
          </a>
        </Button>
      </div>
    )
  }

  return (
    <ChatWindow
      endpoint="/api/agent"
      emoji="📬"
      placeholder={`Hello ${user?.name?.split(" ")[0] || "there"}, how can I help you today?`}
      emptyStateComponent={<InfoCard />}
    />
  )
}
