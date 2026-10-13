import { Navigate, Route, Routes, useLocation, useSearchParams } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import { Shell } from "./Shell";
import { LoadingState } from "./components/ui";
import { AdminPage } from "./pages/AdminPage";
import { CalendarPage } from "./pages/CalendarPage";
import { AgentPage } from "./pages/AgentPage";
import { CommunicationPage } from "./pages/CommunicationPage";
import { CustomersPage } from "./pages/CustomersPage";
import { HomePage } from "./pages/HomePage";
import { KnowledgePage } from "./pages/KnowledgePage";
import { LoginPage } from "./pages/LoginPage";
import { MyWorkPage } from "./pages/MyWorkPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { NotificationsPage } from "./pages/NotificationsPage";
import { PeoplePage } from "./pages/PeoplePage";
import { PricingPage } from "./pages/PricingPage";
import { ReportsPage } from "./pages/ReportsPage";
import { SearchPage } from "./pages/SearchPage";
import { SettingsPage } from "./pages/SettingsPage";
import { VehiclesPage, VehicleDetailPage } from "./pages/VehiclesPage";
import { PerfRoutes } from "./perf/PerfRoutes";
import { ProjectPage } from "./requests/ProjectPage";
import { TeamHomePage } from "./requests/TeamHomePage";
import { ProjectsPage } from "./requests/ProjectsPage";
import { RequestPage } from "./requests/RequestPage";
import { RequestsPage } from "./requests/RequestsPage";

function Protected({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <LoadingState />;
  // مقصد اصلی کاربر را نگه می‌داریم تا بعد از ورود (یا رفرش صفحه) به همان صفحه برگردد
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />;
  return children;
}

/** Search page that reads ?q= from top bar */
function SearchRoute() {
  const [params] = useSearchParams();
  return <SearchPage initialQuery={params.get("q") || ""} />;
}

function HomeRoute() {
  return <HomePage />;
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <Protected>
              <Shell />
            </Protected>
          }
        >
          <Route index element={<HomeRoute />} />
          <Route path="my-work" element={<MyWorkPage />} />
          <Route path="tasks" element={<Navigate to="/my-work" replace />} />
          <Route path="work-items" element={<Navigate to="/projects" replace />} />
          <Route path="work-items/:id" element={<Navigate to="/projects" replace />} />
          <Route path="communication" element={<CommunicationPage />} />
          <Route path="cases" element={<Navigate to="/" replace />} />
          <Route path="people" element={<PeoplePage />} />
          <Route path="teams" element={<Navigate to="/settings" replace />} />
          <Route path="branches" element={<Navigate to="/settings" replace />} />
          <Route path="pricing" element={<PricingPage />} />
          <Route path="vehicles" element={<VehiclesPage />} />
          <Route path="vehicles/:id" element={<VehicleDetailPage />} />
          <Route path="customers" element={<CustomersPage />} />
          <Route path="search" element={<SearchRoute />} />
          <Route path="knowledge" element={<KnowledgePage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="admin" element={<AdminPage />} />
          <Route path="approvals" element={<Navigate to="/my-work" replace />} />
          <Route path="reports" element={<ReportsPage />} />
          <Route path="calendar" element={<CalendarPage />} />
          <Route path="agent" element={<AgentPage />} />
          <Route path="notifications" element={<NotificationsPage />} />
          <Route path="campaigns" element={<Navigate to="/perf/campaigns" replace />} />
          <Route path="campaigns/*" element={<Navigate to="/perf/campaigns" replace />} />
          <Route path="money" element={<Navigate to="/perf/money" replace />} />
          <Route path="sheet" element={<Navigate to="/perf/sheet" replace />} />
          <Route path="stories" element={<Navigate to="/perf/social" replace />} />
          <Route path="perf/*" element={<PerfRoutes />} />
          <Route path="requests" element={<RequestsPage />} />
          <Route path="requests/:id" element={<RequestPage />} />
          <Route path="projects" element={<ProjectsPage />} />
          <Route path="projects/:id" element={<ProjectPage />} />
          <Route path="teams/:teamId" element={<TeamHomePage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </AuthProvider>
  );
}
