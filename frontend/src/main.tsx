import "leaflet/dist/leaflet.css";
import "./index.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { ApiError } from "./api/client";
import App from "./App";
import { AuthProvider } from "./auth/AuthContext";

// Browser error reporting, only when a DSN was given at build time (VITE_SENTRY_DSN).
const sentryDsn: string | undefined = import.meta.env.VITE_SENTRY_DSN;
if (sentryDsn) {
  void import("@sentry/react").then((Sentry) => Sentry.init({ dsn: sentryDsn, environment: import.meta.env.MODE }));
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      retry: (count, err) => !(err instanceof ApiError && err.status < 500) && count < 2,
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
