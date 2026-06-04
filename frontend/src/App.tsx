import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import AppLayout from "./components/Layout/AppLayout";
import Dashboard from "./pages/Dashboard";
import MarketHistory from "./pages/MarketHistory";
import NewsPage from "./pages/News";
import SchedulerPage from "./pages/Scheduler";
import Settings from "./pages/Settings";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/" element={<Navigate to="/market" replace />} />
          <Route path="/market" element={<Dashboard />} />
          <Route path="/market/history" element={<MarketHistory />} />
          <Route path="/news" element={<NewsPage />} />
          <Route path="/scheduler" element={<SchedulerPage />} />
          <Route path="/settings" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
