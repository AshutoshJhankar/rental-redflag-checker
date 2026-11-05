import { useEffect, useState } from "react";
import { analyzeAgreement, getAnalysis, warmUp } from "./api.js";
import UploadPanel from "./components/UploadPanel.jsx";
import Progress from "./components/Progress.jsx";
import ResultView from "./components/ResultView.jsx";

const idFromPath = () => {
  const m = window.location.pathname.match(/^\/r\/([0-9a-f-]{36})$/i);
  return m ? m[1] : null;
};

export default function App() {
  const [state, setState] = useState({ status: "idle" }); // idle | working | done | error
  const [routeId, setRouteId] = useState(idFromPath);

  useEffect(() => {
    warmUp();
    const onPop = () => setRouteId(idFromPath());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  // Open a shared link: /r/<id>
  useEffect(() => {
    if (!routeId) {
      setState((s) => (s.status === "done" ? { status: "idle" } : s));
      return;
    }
    if (state.status === "done" && state.result?.id === routeId) return;
    setState({ status: "working", loadingShared: true });
    getAnalysis(routeId)
      .then((result) => setState({ status: "done", result }))
      .catch((e) => setState({ status: "error", error: e.message }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeId]);

  async function run(file) {
    setState({ status: "working", fileName: file.name });
    try {
      const result = await analyzeAgreement(file);
      setState({ status: "done", result });
      if (result.id) {
        window.history.pushState({}, "", `/r/${result.id}`);
        setRouteId(result.id);
      }
      window.scrollTo({ top: 0 });
    } catch (e) {
      setState({ status: "error", error: e.message });
    }
  }

  function reset() {
    window.history.pushState({}, "", "/");
    setRouteId(null);
    setState({ status: "idle" });
  }

  return (
    <div className="page">
      <header className="topbar">
        <a href="/" className="brand" onClick={(e) => { e.preventDefault(); reset(); }}>
          <span className="brand-mark" aria-hidden>⚑</span> Red-Flag Checker
        </a>
        <span className="topbar-note">for rental agreements</span>
      </header>

      <main className="container">
        {state.status === "idle" && <UploadPanel onFile={run} />}
        {state.status === "working" && <Progress fileName={state.fileName} shared={state.loadingShared} />}
        {state.status === "error" && (
          <div className="card error-card">
            <h2>We couldn't finish that</h2>
            <p>{state.error}</p>
            <button className="btn" onClick={reset}>Try again</button>
          </div>
        )}
        {state.status === "done" && <ResultView result={state.result} onReset={reset} />}
      </main>

      <footer className="footer">
        Automated review to help you ask better questions. Not legal advice.
      </footer>
    </div>
  );
}
