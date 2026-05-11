import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { AuthProvider } from "@/hooks/use-auth"
import { ThemeProvider } from "@/components/theme/theme-provider"
import App from "@/App"
import "./index.css"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider>
      <AuthProvider>
        <App />
      </AuthProvider>
    </ThemeProvider>
  </StrictMode>,
)
