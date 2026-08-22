import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Shell } from "./components/Shell";
import { ToastProvider } from "./components/Toast";
import { Agents } from "./pages/Agents";
import { Compare } from "./pages/Compare";
import { Dashboard } from "./pages/Dashboard";
import { LiveRun } from "./pages/LiveRun";
import { PaperTrading } from "./pages/PaperTrading";
import { Results } from "./pages/Results";
import { Settings } from "./pages/Settings";
import { Showcase } from "./pages/Showcase";

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <Routes>
          <Route element={<Shell />}>
            <Route index element={<Dashboard />} />
            <Route path="live" element={<LiveRun />} />
            <Route path="paper" element={<PaperTrading />} />
            <Route path="results" element={<Results />} />
            <Route path="compare" element={<Compare />} />
            <Route path="agents" element={<Agents />} />
            <Route path="settings" element={<Settings />} />
            <Route path="showcase" element={<Showcase />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </ToastProvider>
    </BrowserRouter>
  );
}
