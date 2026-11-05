import { useRef, useState } from "react";

const SAMPLES = [
  { file: "fair-agreement.pdf", label: "Fair agreement" },
  { file: "typical-agreement.pdf", label: "Typical agreement" },
  { file: "risky-agreement.pdf", label: "Risky agreement" },
];
const MAX_MB = 5;

export default function UploadPanel({ onFile }) {
  const input = useRef(null);
  const [drag, setDrag] = useState(false);
  const [error, setError] = useState("");

  function pick(file) {
    setError("");
    if (!file) return;
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setError("Please choose a PDF file.");
      return;
    }
    if (file.size > MAX_MB * 1024 * 1024) {
      setError(`That file is over ${MAX_MB} MB.`);
      return;
    }
    onFile(file);
  }

  async function trySample(s) {
    const res = await fetch(`/samples/${s.file}`);
    const blob = await res.blob();
    pick(new File([blob], s.file, { type: "application/pdf" }));
  }

  return (
    <>
      <section className="hero">
        <h1>Spot the red flags in your rental agreement before you sign.</h1>
        <p className="lead">
          Upload the PDF. You get the key terms at a glance, every risky clause explained in plain English with
          the exact line it comes from, and what to ask your landlord to change.
        </p>
      </section>

      <section className="card upload-card">
        <div
          className={`dropzone ${drag ? "drag" : ""}`}
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files[0]); }}
          onClick={() => input.current?.click()}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
        >
          <div className="drop-icon" aria-hidden>📄</div>
          <strong>Drop your agreement PDF here</strong>
          <span className="muted">or click to choose a file · text-based PDF · up to {MAX_MB} MB</span>
          <input ref={input} type="file" accept="application/pdf,.pdf" hidden
                 onChange={(e) => pick(e.target.files[0])} />
        </div>
        {error && <p className="inline-error">{error}</p>}

        <div className="samples">
          <span className="muted">No agreement handy? Try a sample:</span>
          {SAMPLES.map((s) => (
            <button key={s.file} className="chip" onClick={() => trySample(s)}>{s.label}</button>
          ))}
        </div>
      </section>

      <section className="how">
        <div className="how-item">
          <span className="how-num">1</span>
          <h3>Read every clause</h3>
          <p>The agreement is split into clauses. Phone, email, PAN and Aadhaar numbers are masked before the AI sees them.</p>
        </div>
        <div className="how-item">
          <span className="how-num">2</span>
          <h3>Check the AI's work</h3>
          <p>Every flag must quote your document word for word. If the quote isn't in your agreement, the flag is dropped.</p>
        </div>
        <div className="how-item">
          <span className="how-num">3</span>
          <h3>Do the math in code</h3>
          <p>Deposit-to-rent ratio, lock-in and notice periods are checked by fixed rules, not guessed by the AI.</p>
        </div>
      </section>
      <p className="privacy muted">Your PDF is read in memory and never stored. Only the results are saved, so you can share a link (deleted after 30 days).</p>
    </>
  );
}
