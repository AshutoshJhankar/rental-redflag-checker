import { useState } from "react";
import { money, months, percent } from "../format.js";

const SEV_LABEL = { high: "High risk", medium: "Worth negotiating", low: "Minor" };
const LEVEL_TEXT = {
  low: "Looks fairly balanced",
  moderate: "A few things to negotiate",
  high: "Several clauses work against you",
};

function ScoreRing({ score, level }) {
  const r = 44;
  const c = 2 * Math.PI * r;
  return (
    <svg className={`ring ring-${level}`} viewBox="0 0 110 110" role="img" aria-label={`Risk score ${score} of 100`}>
      <circle cx="55" cy="55" r={r} className="ring-track" />
      <circle cx="55" cy="55" r={r} className="ring-value"
              strokeDasharray={`${(score / 100) * c} ${c}`} transform="rotate(-90 55 55)" />
      <text x="55" y="53" textAnchor="middle" className="ring-score">{score}</text>
      <text x="55" y="72" textAnchor="middle" className="ring-label">/ 100</text>
    </svg>
  );
}

function Term({ label, term, format, extra }) {
  const ok = term && term.verified && term.value != null;
  return (
    <div className={`term ${ok ? "" : "term-missing"}`} title={ok && term.quote ? `“${term.quote}”` : undefined}>
      <span className="term-label">{label}</span>
      <span className="term-value">
        {ok ? format(term.value) : term && term.value != null ? "Couldn't verify" : "Not stated"}
      </span>
      {ok && extra && <span className="term-extra">{extra}</span>}
      {ok && term.page && <span className="term-ref">Clause {term.clause_id} · p.{term.page}</span>}
    </div>
  );
}

function FlagCard({ flag }) {
  return (
    <article className={`flag flag-${flag.severity}`}>
      <div className="flag-head">
        <span className={`pill pill-${flag.severity}`}>{SEV_LABEL[flag.severity]}</span>
        <h3>{flag.title}</h3>
      </div>
      <p>{flag.explanation}</p>
      {flag.quote ? (
        <blockquote>
          “{flag.quote}”
          <cite>
            Clause {flag.clause_id} · page {flag.page} ·{" "}
            {flag.source === "rule" ? "checked by rule" : "quote verified in your document"}
          </cite>
        </blockquote>
      ) : (
        <p className="missing-note">Not found anywhere in your agreement.</p>
      )}
      <p className="ask"><strong>Ask for:</strong> {flag.suggestion}</p>
    </article>
  );
}

export default function ResultView({ result, onReset }) {
  const [copied, setCopied] = useState("");
  const t = result.key_terms;
  const counts = result.flags.reduce((acc, f) => ({ ...acc, [f.severity]: (acc[f.severity] || 0) + 1 }), {});
  const asks = result.flags.map((f) => f.suggestion);

  async function copy(text, what) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(what);
      setTimeout(() => setCopied(""), 2000);
    } catch {
      setCopied("");
    }
  }

  return (
    <div className="result">
      <section className="card summary">
        <ScoreRing score={result.risk_score} level={result.risk_level} />
        <div className="summary-text">
          <span className="muted small">{result.file_name} · {result.page_count} page(s) · {result.clause_count} clauses</span>
          <h1>{LEVEL_TEXT[result.risk_level]}</h1>
          <p className="counts">
            <span className="pill pill-high">{counts.high || 0} high</span>
            <span className="pill pill-medium">{counts.medium || 0} to negotiate</span>
            <span className="pill pill-low">{counts.low || 0} minor</span>
          </p>
          <div className="actions">
            {result.id && (
              <button className="btn" onClick={() => copy(window.location.href, "link")}>
                {copied === "link" ? "Link copied ✓" : "Copy share link"}
              </button>
            )}
            <button className="btn btn-ghost" onClick={onReset}>Check another agreement</button>
          </div>
        </div>
      </section>

      <section className="card">
        <h2>Key terms</h2>
        <div className="terms">
          <Term label="Monthly rent" term={t.monthly_rent} format={money} />
          <Term label="Security deposit" term={t.security_deposit} format={money}
                extra={result.deposit_months ? `= ${result.deposit_months} months of rent` : null} />
          <Term label="Maintenance" term={t.maintenance_monthly} format={(v) => `${money(v)}/month`} />
          <Term label="Agreement length" term={t.agreement_months} format={months} />
          <Term label="Lock-in" term={t.lock_in_months} format={months} />
          <Term label="Your notice period" term={t.notice_tenant_months} format={months} />
          <Term label="Owner's notice period" term={t.notice_landlord_months} format={months} />
          <Term label="Rent increase" term={t.rent_escalation_percent} format={percent} />
        </div>
      </section>

      <section>
        <h2 className="section-title">
          {result.flags.length ? `${result.flags.length} thing${result.flags.length > 1 ? "s" : ""} to look at` : "No red flags found"}
        </h2>
        {result.flags.length === 0 && (
          <div className="card"><p>Nothing stood out as unusual or one-sided. Still read the whole agreement before signing.</p></div>
        )}
        <div className="flags">
          {result.flags.map((f, i) => <FlagCard key={i} flag={f} />)}
        </div>
        {result.discarded_flags > 0 && (
          <p className="muted small dropped">
            {result.discarded_flags} AI suggestion{result.discarded_flags > 1 ? "s were" : " was"} dropped because the
            quoted text couldn't be found in your agreement.
          </p>
        )}
      </section>

      {asks.length > 0 && (
        <section className="card asks">
          <div className="asks-head">
            <h2>Questions for your landlord</h2>
            <button className="btn btn-ghost btn-sm"
                    onClick={() => copy(asks.map((a, i) => `${i + 1}. ${a}`).join("\n"), "asks")}>
              {copied === "asks" ? "Copied ✓" : "Copy list"}
            </button>
          </div>
          <ol>{asks.map((a, i) => <li key={i}>{a}</li>)}</ol>
        </section>
      )}

      <p className="disclaimer muted small">
        {result.disclaimer}
        {result.masked_items > 0 && ` ${result.masked_items} personal detail(s) were masked before analysis.`}
      </p>
    </div>
  );
}
