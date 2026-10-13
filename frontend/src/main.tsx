import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { ConfirmProvider } from "./components/ui/ConfirmDialog";
import { ToastProvider } from "./components/ui/Toast";
import { LocaleProvider } from "./i18n";
// فونت و پالت از کیت برند ستوده؛ فایل‌ها محلی‌اند و به اینترنت نیاز ندارند
import "../../assets/sotoodeh-brand-kit/code/fonts.css";
import "../../assets/sotoodeh-brand-kit/code/brand.css";
import "./styles.css";

const queryClient = new QueryClient();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <LocaleProvider>
        <ToastProvider>
          <ConfirmProvider>
            <BrowserRouter>
              <App />
            </BrowserRouter>
          </ConfirmProvider>
        </ToastProvider>
      </LocaleProvider>
    </QueryClientProvider>
  </StrictMode>,
);
