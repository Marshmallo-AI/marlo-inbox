import { useState, useEffect, useCallback, useRef } from "react"
import { useQueryState } from "nuqs"
import { PlusCircle, MessageSquare, Loader2, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

interface ThreadValue {
  messages?: Array<{ content: unknown; type: string }>
}

interface Thread {
  thread_id: string
  created_at: string
  updated_at: string
  metadata: Record<string, unknown>
  values?: ThreadValue
}

interface ThreadSidebarProps {
  className?: string
}

export function ThreadSidebar({ className }: ThreadSidebarProps) {
  const [urlThreadId, setUrlThreadId] = useQueryState("threadId")
  const [threads, setThreads] = useState<Thread[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const lastFetchTimeRef = useRef<number>(0)
  const fetchDebounceMs = 2000

  const fetchThreads = useCallback(async () => {
    try {
      setIsLoading(true)
      setError(null)
      lastFetchTimeRef.current = Date.now()
      const response = await fetch("/api/agent/threads/search", {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          limit: 50,
          offset: 0,
        }),
      })
      if (!response.ok) {
        throw new Error("Failed to fetch threads")
      }
      const data = await response.json()
      setThreads(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load threads")
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchThreads()
  }, [fetchThreads])

  useEffect(() => {
    if (urlThreadId && !threads.find(t => t.thread_id === urlThreadId)) {
      const now = Date.now()
      if (now - lastFetchTimeRef.current < fetchDebounceMs) {
        return
      }
      lastFetchTimeRef.current = now
      fetchThreads()
    }
  }, [urlThreadId, threads, fetchThreads])

  const handleNewChat = useCallback(() => {
    setUrlThreadId(null)
  }, [setUrlThreadId])

  const handleSelectThread = useCallback((threadId: string) => {
    setUrlThreadId(threadId)
  }, [setUrlThreadId])

  const handleDeleteThread = useCallback(async (threadId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      const response = await fetch(`/api/agent/threads/${threadId}`, {
        method: "DELETE",
        credentials: "include",
      })
      if (response.ok) {
        setThreads(prev => prev.filter(t => t.thread_id !== threadId))
        if (urlThreadId === threadId) {
          setUrlThreadId(null)
        }
      }
    } catch (err) {
      console.error("Failed to delete thread:", err)
    }
  }, [urlThreadId, setUrlThreadId])

  const getThreadName = (thread: Thread): string => {
    const metadataName = thread.metadata?.thread_name || thread.metadata?.name
    if (metadataName && typeof metadataName === "string") {
      return metadataName
    }

    const messages = thread.values?.messages
    if (messages && messages.length > 0) {
      const firstHumanMessage = messages.find(m => m.type === "human")
      if (firstHumanMessage?.content) {
        let content = firstHumanMessage.content
        if (typeof content === "object") {
          if (Array.isArray(content)) {
            const textBlock = content.find((c: { type: string; text?: string }) => c.type === "text")
            content = textBlock?.text || ""
          } else if ("text" in content) {
            content = (content as { text: string }).text
          } else {
            content = ""
          }
        }
        if (typeof content === "string" && content.length > 0) {
          return content.length > 40 ? content.slice(0, 40) + "..." : content
        }
      }
    }

    return "New conversation"
  }

  const formatDate = (dateString: string) => {
    const date = new Date(dateString)
    const now = new Date()
    const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24))

    if (diffDays === 0) {
      return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    } else if (diffDays === 1) {
      return "Yesterday"
    } else if (diffDays < 7) {
      return date.toLocaleDateString([], { weekday: "short" })
    } else {
      return date.toLocaleDateString([], { month: "short", day: "numeric" })
    }
  }

  return (
    <div className={cn("flex flex-col h-full bg-white border-r border-gray-200", className)}>
      <div className="p-4 border-b border-gray-200 shrink-0">
        <Button
          onClick={handleNewChat}
          className="w-full justify-start gap-2 bg-gray-900 text-white hover:bg-gray-800"
        >
          <PlusCircle className="w-4 h-4" />
          New Chat
        </Button>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto">
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
          </div>
        ) : error ? (
          <div className="px-4 py-4 text-sm text-red-600">{error}</div>
        ) : threads.length === 0 ? (
          <div className="px-4 py-8 text-center text-sm text-gray-500">
            No conversations yet
          </div>
        ) : (
          <div className="py-2">
            {threads.map((thread) => (
              <div
                key={thread.thread_id}
                onClick={() => handleSelectThread(thread.thread_id)}
                className={cn(
                  "group flex items-center gap-3 px-4 py-3 mx-2 rounded-lg cursor-pointer",
                  "hover:bg-gray-100 transition-colors",
                  urlThreadId === thread.thread_id && "bg-gray-100"
                )}
              >
                <MessageSquare className="w-4 h-4 shrink-0 text-gray-500" />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-gray-900 truncate">
                    {getThreadName(thread)}
                  </div>
                  <div className="text-xs text-gray-500">
                    {formatDate(thread.updated_at || thread.created_at)}
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="opacity-0 group-hover:opacity-100 shrink-0 hover:bg-gray-200"
                  onClick={(e) => handleDeleteThread(thread.thread_id, e)}
                >
                  <Trash2 className="w-3.5 h-3.5 text-gray-500" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="p-4 border-t border-gray-200 text-xs text-gray-500 text-center shrink-0">
        {threads.length} conversation{threads.length !== 1 ? "s" : ""}
      </div>
    </div>
  )
}
