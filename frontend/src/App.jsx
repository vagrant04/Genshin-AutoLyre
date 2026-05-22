import { Route, Routes } from "react-router-dom";
import SearchPage from "./pages/SearchPage.jsx";
import ResultsPage from "./pages/ResultsPage.jsx";
import TrackConfigPage from "./pages/TrackConfigPage.jsx";
import ScorePage from "./pages/ScorePage.jsx";

export default function App() {
  return (
    <div className="min-h-screen">
      <Routes>
        <Route path="/" element={<SearchPage />} />
        <Route path="/results" element={<ResultsPage />} />
        <Route path="/tracks" element={<TrackConfigPage />} />
        <Route path="/score" element={<ScorePage />} />
      </Routes>
    </div>
  );
}
