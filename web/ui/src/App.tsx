import { useEffect, useState } from "react";
import { Route, Routes } from "react-router-dom";
import { api } from "./api";
import type { Config } from "./types";
import { Nav } from "./components/Nav";
import { Disclaimer } from "./components/Disclaimer";
import { ClassifyScreen } from "./screens/ClassifyScreen";
import { TriageScreen } from "./screens/TriageScreen";
import { AuditScreen } from "./screens/AuditScreen";

export default function App() {
  const [config, setConfig] = useState<Config | null>(null);

  useEffect(() => {
    api.config().then(setConfig).catch(() => setConfig(null));
  }, []);

  return (
    <>
      <Nav config={config} />
      <Routes>
        <Route path="/" element={<ClassifyScreen config={config} />} />
        <Route path="/triage" element={<TriageScreen />} />
        <Route path="/audit/:id" element={<AuditScreen />} />
      </Routes>
      <div className="wrap" style={{ paddingTop: 0 }}>
        <Disclaimer />
      </div>
    </>
  );
}
