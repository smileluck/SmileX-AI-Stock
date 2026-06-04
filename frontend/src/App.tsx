import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import AppLayout from "./components/Layout/AppLayout";
import Dashboard from "./pages/Dashboard";
import MarketHistory from "./pages/MarketHistory";
import MarketAnalysis from "./pages/MarketAnalysis";
import SectorOverview from "./pages/SectorOverview";
import SectorHistory from "./pages/SectorHistory";
import NewsPage from "./pages/News";
import SchedulerPage from "./pages/Scheduler";
import LLMConfig from "./pages/LLMConfig";
import AIChat from "./pages/AIChat";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/" element={<Navigate to="/market" replace />} />
          <Route path="/market" element={<Dashboard />} />
          <Route path="/market/analysis" element={<MarketAnalysis />} />
          <Route path="/market/history" element={<MarketHistory />} />
          <Route path="/sector" element={<Navigate to="/sector/today" replace />} />
          <Route path="/sector/today" element={<SectorOverview />} />
          <Route path="/sector/history" element={<SectorHistory />} />
          <Route path="/news" element={<NewsPage />} />
          <Route path="/scheduler" element={<SchedulerPage />} />
          <Route path="/ai-assistant" element={<Navigate to="/ai-assistant/llm-config" replace />} />
          <Route path="/ai-assistant/llm-config" element={<LLMConfig />} />
          <Route path="/ai-assistant/chat" element={<AIChat />} />
          <Route path="/settings" element={<Navigate to="/ai-assistant/llm-config" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
