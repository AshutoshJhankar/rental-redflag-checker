import { useEffect, useState } from "react";

const STEPS = ["Reading the PDF", "Splitting into clauses", "Reviewing with AI", "Verifying every quote"];

export default function Progress({ fileName, shared }) {
  const [step, setStep] = useState(0);
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    const t = setInterval(() => setStep((s) => Math.min(s + 1, STEPS.length - 1)), 2500);
    const s = setTimeout(() => setSlow(true), 12000);
    return () => { clearInterval(t); clearTimeout(s); };
  }, []);

  return (
    <div className="card progress-card" aria-live="polite">
      <div className="spinner" aria-hidden />
      <h2>{shared ? "Opening shared analysis…" : `Checking ${fileName || "your agreement"}…`}</h2>
      {!shared && (
        <ol className="steps">
          {STEPS.map((label, i) => (
            <li key={label} className={i < step ? "done" : i === step ? "active" : ""}>{label}</li>
          ))}
        </ol>
      )}
      {slow && (
        <p className="muted small">
          Still working. The free server sleeps when idle, so the first request can take up to a minute.
        </p>
      )}
    </div>
  );
}
