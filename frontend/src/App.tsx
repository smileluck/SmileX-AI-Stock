import { BrowserRouter, Routes, Route } from "react-router-dom";
import AppLayout from "./components/Layout/AppLayout";
import Dashboard from "./pages/Dashboard";
import NewsPage from "./pages/News";
import SchedulerPage from "./pages/Scheduler";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/news" element={<NewsPage />} />
          <Route path="/scheduler" element={<SchedulerPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
