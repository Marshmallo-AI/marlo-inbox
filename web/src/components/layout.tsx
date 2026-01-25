import { Routes, Route } from "react-router"
import { Mail, Github } from "lucide-react"
import { Button } from "@/components/ui/button"
import UserButton from "@/components/auth0/user-button"

import ChatPage from "@/pages/ChatPage"
import ClosePage from "@/pages/ClosePage"
import useAuth, { getLogoutUrl } from "@/lib/use-auth"

export default function Layout() {
  const { user } = useAuth()

  return (
    <div className="bg-background grid grid-rows-[auto_1fr] h-[100dvh]">
      <header className="border-b border-border">
        <div className="flex items-center justify-between h-14 px-4 max-w-screen-xl mx-auto">
          <div className="flex items-center gap-4">
            <a href="/" className="flex items-center gap-2">
              <div className="p-1.5 rounded-md bg-primary/10">
                <Mail className="h-5 w-5 text-primary" />
              </div>
              <span className="font-semibold text-foreground">Inbox Pilot</span>
            </a>
          </div>

          <div className="flex items-center gap-3">
            {user && (
              <UserButton user={user} logoutUrl={getLogoutUrl()} />
            )}
            <Button asChild variant="ghost" size="icon-sm">
              <a
                href="https://github.com/marlo-ai/marlo-inbox"
                target="_blank"
                rel="noopener noreferrer"
              >
                <Github className="h-4 w-4" />
              </a>
            </Button>
          </div>
        </div>
      </header>

      <main className="relative overflow-hidden">
        <div className="absolute inset-0">
          <Routes>
            <Route path="/" element={<ChatPage />} />
            <Route path="/close" element={<ClosePage />} />
          </Routes>
        </div>
      </main>
    </div>
  )
}
