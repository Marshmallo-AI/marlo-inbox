import { useEffect } from "react"

export default function ClosePage() {
  useEffect(() => {
    window.close()
  }, [])

  return (
    <div className="flex flex-col items-center justify-center min-h-[50vh] my-auto gap-4 px-4">
      <h2 className="text-xl font-semibold text-foreground">
        Authorization Complete
      </h2>
      <p className="text-muted-foreground text-center">
        You can close this window and return to the chat.
      </p>
    </div>
  )
}
