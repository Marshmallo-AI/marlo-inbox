import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { QueryClientProvider, QueryClient } from "@tanstack/react-query"
import { BrowserRouter } from "react-router"
import { NuqsAdapter } from "nuqs/adapters/react"
import { Toaster } from "@/components/ui/sonner"
import Layout from "@/components/layout"
import "./index.css"

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30 * 1000,
      gcTime: 5 * 60 * 1000,
      refetchOnWindowFocus: false,
    },
  },
})

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <NuqsAdapter>
          <Layout />
        </NuqsAdapter>
      </BrowserRouter>
    </QueryClientProvider>
    <Toaster richColors />
  </StrictMode>
)
