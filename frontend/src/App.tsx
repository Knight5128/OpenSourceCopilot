import { useEffect, useState } from "react";

export default function App() {
  const [status, setStatus] = useState<string>("checking...");

  useEffect(() => {
    fetch("/api/v1/health")
      .then((r) => r.json())
      .then((d) => setStatus(d.status))
      .catch(() => setStatus("backend unreachable"));
  }, []);

  return (
    <main
      style={{
        fontFamily: "system-ui, -apple-system, sans-serif",
        maxWidth: 720,
        margin: "4rem auto",
        padding: "0 1.5rem",
        lineHeight: 1.6,
      }}
    >
      <h1>OpenSourceCopilot</h1>
      <p>开源贡献者 Onboarding 副驾 · KG + HybridRAG + Agent</p>
      <p>
        Backend status: <strong>{status}</strong>
      </p>
      <p style={{ color: "#888", marginTop: "3rem" }}>
        Scaffold ready. See <code>docs/proposal.md</code> for the full plan.
      </p>
    </main>
  );
}
