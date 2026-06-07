import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import AppLayout from "./components/Layout/AppLayout";
import Dashboard from "./pages/Dashboard";
import MarketHistory from "./pages/MarketHistory";
import MarketAnalysis from "./pages/MarketAnalysis";
import SectorOverview from "./pages/SectorOverview";
import SectorHistory from "./pages/SectorHistory";
import SectorAnalysis from "./pages/SectorAnalysis";
import NewsPage from "./pages/News";
import SchedulerPage from "./pages/Scheduler";
import LLMConfig from "./pages/LLMConfig";
import AIChat from "./pages/AIChat";
import StockOverview from "./pages/stock/StockOverview";
import StockLimitUp from "./pages/stock/StockLimitUp";
import StockRecommendation from "./pages/stock/StockRecommendation";
import StockHistory from "./pages/stock/StockHistory";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/" element={<Navigate to="/market" replace />} />
          <Route path="/market" element={<Dashboard />} />
          <Route path="/market/analysis" element={<Navigate to="/analysis/market" replace />} />
          <Route path="/market/history" element={<MarketHistory />} />
          <Route path="/analysis" element={<Navigate to="/analysis/market" replace />} />
          <Route path="/analysis/market" element={<MarketAnalysis />} />
          <Route path="/analysis/sector" element={<SectorAnalysis />} />
          <Route path="/sector" element={<Navigate to="/sector/today" replace />} />
          <Route path="/sector/today" element={<SectorOverview />} />
          <Route path="/sector/history" element={<SectorHistory />} />
          <Route path="/stock" element={<Navigate to="/stock/overview" replace />} />
          <Route path="/stock/overview" element={<StockOverview />} />
          <Route path="/stock/limit-up" element={<StockLimitUp />} />
          <Route path="/stock/recommendation" element={<StockRecommendation />} />
          <Route path="/stock/history" element={<StockHistory />} />
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
