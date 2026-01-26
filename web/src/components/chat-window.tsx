import { useState, useRef, useCallback, useEffect } from "react"
import type { FormEvent, ReactNode } from "react"
import { toast } from "sonner"
import { StickToBottom, useStickToBottomContext } from "use-stick-to-bottom"
import { ArrowDown, ArrowUpIcon, LoaderCircle } from "lucide-react"
import { useQueryState } from "nuqs"
import { useStream } from "@langchain/langgraph-sdk/react"
import { type Message } from "@langchain/langgraph-sdk"

import { ChatMessageBubble } from "@/components/chat-message-bubble"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

function ChatMessages(props: {
  messages: Message[]
  emptyStateComponent: ReactNode
  aiEmoji?: string
  className?: string
}) {
  return (
    <div className="flex flex-col max-w-[768px] mx-auto pb-12 w-full">
      {props.messages.map((m) => {
        return (
          <ChatMessageBubble
            key={m.id}
            message={m}
            aiEmoji={props.aiEmoji}
            allMessages={props.messages}
          />
        )
      })}
    </div>
  )
}

function ScrollToBottom(props: { className?: string }) {
  const { isAtBottom, scrollToBottom } = useStickToBottomContext()

  if (isAtBottom) return null
  return (
    <Button
      variant="outline"
      className={props.className}
      onClick={() => scrollToBottom()}
    >
      <ArrowDown className="w-4 h-4" />
      <span>Scroll to bottom</span>
    </Button>
  )
}

function ChatInput(props: {
  onSubmit: (e: FormEvent<HTMLFormElement>) => void
  value: string
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void
  loading?: boolean
  placeholder?: string
  children?: ReactNode
  className?: string
}) {
  return (
    <form
      onSubmit={(e) => {
        e.stopPropagation()
        e.preventDefault()
        props.onSubmit(e)
      }}
      className={cn("flex w-full flex-col", props.className)}
    >
      <div className="border border-input bg-background rounded-lg flex flex-col gap-2 max-w-[768px] w-full mx-auto shadow-sm">
        <input
          value={props.value}
          placeholder={props.placeholder}
          onChange={props.onChange}
          className="border-none outline-none bg-transparent p-4 text-foreground placeholder:text-muted-foreground"
          autoFocus
        />

        <div className="flex justify-between ml-4 mr-2 mb-2">
          <div className="flex gap-3">{props.children}</div>

          <Button
            className="rounded-full p-1.5 h-fit"
            type="submit"
            disabled={props.loading}
            size="icon-sm"
          >
            {props.loading ? (
              <LoaderCircle className="animate-spin" />
            ) : (
              <ArrowUpIcon size={14} />
            )}
          </Button>
        </div>
      </div>
    </form>
  )
}

function StickyToBottomContent(props: {
  content: ReactNode
  footer?: ReactNode
  className?: string
  contentClassName?: string
}) {
  const context = useStickToBottomContext()

  return (
    <div
      ref={context.scrollRef}
      style={{ width: "100%", height: "100%" }}
      className={cn("grid grid-rows-[1fr,auto]", props.className)}
    >
      <div ref={context.contentRef} className={props.contentClassName}>
        {props.content}
      </div>

      {props.footer}
    </div>
  )
}

export function ChatWindow(props: {
  endpoint: string
  emptyStateComponent: ReactNode
  placeholder?: string
  emoji?: string
}) {
  const [urlThreadId, setUrlThreadId] = useQueryState("threadId")
  const [input, setInput] = useState("")
  const [stableThreadId, setStableThreadId] = useState<string | null>(urlThreadId)

  const isStreamingRef = useRef(false)
  const lastUrlUpdateRef = useRef<string | null>(null)
  const pendingThreadIdRef = useRef<string | null>(null)

  useEffect(() => {
    if (isStreamingRef.current) return

    if (lastUrlUpdateRef.current !== null && lastUrlUpdateRef.current === urlThreadId) {
      return
    }

    if (urlThreadId !== stableThreadId) {
      lastUrlUpdateRef.current = null
      setStableThreadId(urlThreadId)
    }
  }, [urlThreadId, stableThreadId])

  const fetchWithCredentials = (url: string | URL | Request, options = {}) => {
    return fetch(url, {
      ...options,
      credentials: "include",
    })
  }

  const handleThreadId = useCallback((newThreadId: string) => {
    if (isStreamingRef.current) {
      pendingThreadIdRef.current = newThreadId
      setStableThreadId(newThreadId)
    } else {
      lastUrlUpdateRef.current = newThreadId
      setUrlThreadId(newThreadId)
    }
  }, [setUrlThreadId])

  const chat = useStream({
    apiUrl: `${window.location.origin}${props.endpoint}`,
    assistantId: "inbox",
    threadId: stableThreadId,
    callerOptions: {
      fetch: fetchWithCredentials,
    },
    onThreadId: handleThreadId,
    onError: (error: unknown) => {
      isStreamingRef.current = false
      if (pendingThreadIdRef.current) {
        lastUrlUpdateRef.current = pendingThreadIdRef.current
        setUrlThreadId(pendingThreadIdRef.current)
        pendingThreadIdRef.current = null
      }
      console.error("Error: ", error)
      const message = error instanceof Error ? error.message : String(error)
      toast.error("Error while processing your request", {
        description: message,
      })
    },
    onFinish: () => {
      isStreamingRef.current = false
      if (pendingThreadIdRef.current) {
        lastUrlUpdateRef.current = pendingThreadIdRef.current
        setUrlThreadId(pendingThreadIdRef.current)
        pendingThreadIdRef.current = null
      }
    },
  })

  function isChatLoading(): boolean {
    return chat.isLoading
  }

  async function sendMessage(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (isChatLoading()) return

    isStreamingRef.current = true

    chat.submit(
      { messages: [{ type: "human", content: input }] },
      {
        optimisticValues: (prev) => ({
          messages: [
            ...((prev?.messages as []) ?? []),
            { type: "human", content: input, id: "temp" },
          ],
        }),
      }
    )
    setInput("")
  }

  return (
    <StickToBottom className="h-full">
      <StickyToBottomContent
        className="absolute inset-0"
        contentClassName="py-8 px-2"
        content={
          chat.messages.length === 0 ? (
            <div>{props.emptyStateComponent}</div>
          ) : (
            <ChatMessages
              aiEmoji={props.emoji}
              messages={chat.messages}
              emptyStateComponent={props.emptyStateComponent}
            />
          )
        }
        footer={
          <div className="sticky bottom-8 px-2">
            <ScrollToBottom className="absolute bottom-full left-1/2 -translate-x-1/2 mb-4" />
            <ChatInput
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onSubmit={sendMessage}
              loading={isChatLoading()}
              placeholder={props.placeholder ?? "What can I help you with?"}
            />
          </div>
        }
      />
    </StickToBottom>
  )
}
