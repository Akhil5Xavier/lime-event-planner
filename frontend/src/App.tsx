import { lazy } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { RequireAuth } from "./auth/AuthContext";
import Layout from "./components/Layout";
import LoginPage from "./pages/LoginPage";

// Loaded on demand so the login page doesn't download FullCalendar and Leaflet.
const CalendarPage = lazy(() => import("./pages/CalendarPage"));
const DayPage = lazy(() => import("./pages/DayPage"));
const VenuesPage = lazy(() => import("./pages/VenuesPage"));
const AdminPage = lazy(() => import("./pages/AdminPage"));

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<CalendarPage />} />
        <Route path="day/:date" element={<DayPage />} />
        <Route path="venues" element={<VenuesPage />} />
        <Route
          path="admin"
          element={
            <RequireAuth admin>
              <AdminPage />
            </RequireAuth>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
