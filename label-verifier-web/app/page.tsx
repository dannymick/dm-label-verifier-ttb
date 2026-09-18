"use client";

import Image from "next/image";
import { ChangeEvent, FormEvent, useEffect, useState } from "react";

type FieldStatus = "match" | "review" | "mismatch" | "missing";
type FieldResult = { field: string; expected: string; observed: string | null; status: FieldStatus; reason: string; evidence: string[]; similarity: number | null };
type AnalysisResult = { overall_status: "match" | "review" | "mismatch"; processing_ms: number; ocr_text: string; fields: FieldResult[]; limitations: string[] };
type BatchResult = { items: { filename: string; result: AnalysisResult | null; error: string | null }[] };

const labels: Record<string, string> = { brand_name: "Brand name", class_type: "Class / type", alcohol_content: "Alcohol content", net_contents: "Net contents", country_of_origin: "Country of origin", government_warning: "Government warning" };
const api = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const formKeys = ["brand_name", "class_type", "alcohol_content", "net_contents", "country_of_origin"] as const;

function Status({ status }: { status: FieldStatus }) {
  const icon = status === "match" ? "✓" : status === "review" || status === "missing" ? "!" : "×";
  const label = status === "missing" ? "Missing" : status[0].toUpperCase() + status.slice(1);
  return <span className={["status", status].join(" ")}><span aria-hidden="true">{icon}</span>{label}</span>;
}

export default function Home() {
  const [form, setForm] = useState({ brand_name: "OLD TOM DISTILLERY", class_type: "Kentucky Straight Bourbon Whiskey", alcohol_content: "45%", net_contents: "750 mL", country_of_origin: "United States" });
  const [image, setImage] = useState<File | null>(null);
  const [batchFiles, setBatchFiles] = useState<File[]>([]);
  const [preview, setPreview] = useState<string | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [batchResult, setBatchResult] = useState<BatchResult | null>(null);
  const [batchElapsedMs, setBatchElapsedMs] = useState<number | null>(null);
  const [expandedBatchRows, setExpandedBatchRows] = useState<Set<number>>(() => new Set());
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  function update(key: keyof typeof form, value: string) {
    setForm((current) => ({ ...current, [key]: value }));
    setResult(null);
    setBatchResult(null);
    setBatchElapsedMs(null);
  }

  function selectImage(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    if (preview) URL.revokeObjectURL(preview);
    setImage(file);
    setPreview(file ? URL.createObjectURL(file) : null);
    setResult(null);
    setError(null);
  }

  function selectBatch(event: ChangeEvent<HTMLInputElement>) {
    setBatchFiles(Array.from(event.target.files ?? []));
    setBatchResult(null);
    setBatchElapsedMs(null);
    setExpandedBatchRows(new Set());
    setError(null);
  }

  async function request(path: string, body: FormData, timeout: number) {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(api + path, { method: "POST", body, signal: controller.signal });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error?.message ?? "The service could not analyze this label.");
      return data;
    } finally {
      window.clearTimeout(timer);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setResult(null);
    if (!image) { setError("Choose a JPEG or PNG label image before analyzing."); return; }
    setLoading(true);
    const data = new FormData();
    data.append("image", image);
    data.append("application", JSON.stringify(form));
    try {
      setResult(await request("/analyze", data, 15000));
    } catch (cause) {
      setError(cause instanceof DOMException && cause.name === "AbortError" ? "The analysis took too long. Please try a smaller or clearer image." : cause instanceof Error ? cause.message : "The service could not analyze this label.");
    } finally {
      setLoading(false);
    }
  }

  async function submitBatch() {
    setError(null);
    setBatchResult(null);
    setBatchElapsedMs(null);
    setExpandedBatchRows(new Set());
    if (!batchFiles.length || batchFiles.length > 20) { setError("Choose one to 20 JPEG or PNG images before running a batch."); return; }
    setLoading(true);
    const data = new FormData();
    batchFiles.forEach((file) => data.append("images", file));
    data.append("application", JSON.stringify(form));
    try {
      const started = performance.now();
      const response = await request("/batch", data, 60000);
      setBatchElapsedMs(Math.round(performance.now() - started));
      setBatchResult(response);
    } catch (cause) {
      setError(cause instanceof DOMException && cause.name === "AbortError" ? "The batch took too long. Try fewer or smaller images." : cause instanceof Error ? cause.message : "The service could not analyze this batch.");
    } finally {
      setLoading(false);
    }
  }

  const heading = result?.overall_status === "match" ? "✓ Checked fields match" : result?.overall_status === "review" ? "! Agent review needed" : "× Mismatch found";
  function toggleBatchRow(index: number) {
    setExpandedBatchRows((current) => {
      const next = new Set(current);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  }

  return <main>
    <header><p className="eyebrow">TTB prototype</p><h1>Alcohol label verifier</h1><p className="intro">Compare a label image with application details. Results support an agent&apos;s review and do not approve a label.</p></header>
    <form onSubmit={submit}>
      <section><div className="section-title"><p className="step">1</p><div><h2>Application details</h2><p>Enter the details submitted with the application.</p></div></div>
        <div className="fields">{formKeys.map((key) => <label className={key === "country_of_origin" ? "full" : ""} key={key}>{labels[key]} {key === "country_of_origin" ? <span>Optional</span> : null}<input required={key !== "country_of_origin"} value={form[key]} onChange={(event) => update(key, event.target.value)} /></label>)}</div>
      </section>
      <section><div className="section-title"><p className="step">2</p><div><h2>Label image</h2><p>Use a clear, straight-on JPEG or PNG under 5 MiB.</p></div></div>
        <label className="upload"><input type="file" accept="image/jpeg,image/png" onChange={selectImage} />{preview ? <><Image src={preview} alt="Selected label preview" width={640} height={480} unoptimized /><span>Choose a different image</span></> : <><strong>Choose label image</strong><span>JPEG or PNG, maximum 5 MiB</span></>}</label>
      </section>
      {error ? <p role="alert" className="error">{error}</p> : null}
      <button disabled={loading} type="submit">{loading ? "Analyzing label..." : "Analyze label"}</button>
    </form>
    <section className="batch"><h2>Batch check</h2><p>Check up to 20 labels against the same application details. Files run one at a time.</p>
      <label className="batch-input">Choose batch images<input type="file" accept="image/jpeg,image/png" multiple onChange={selectBatch} /></label>
      {batchFiles.length ? <p>{batchFiles.length} image{batchFiles.length === 1 ? "" : "s"} ready.</p> : null}
      <button disabled={loading} type="button" onClick={submitBatch}>{loading ? "Analyzing..." : "Analyze batch"}</button>
    </section>
    {batchResult ? <section className="results" aria-live="polite">
      <div className="batch-results-heading"><h2>Batch results</h2>{batchElapsedMs !== null ? <p>Batch completed in {(batchElapsedMs / 1000).toFixed(1)} seconds.</p> : null}</div>
      <div className="batch-table">
        <div className="batch-head"><span>File</span><span>Status</span><span>Details</span></div>
        {batchResult.items.map((item, index) => {
          const issues = item.result?.fields.filter((field) => field.status !== "match") ?? [];
          const hasDetails = Boolean(item.error || issues.length);
          const expanded = expandedBatchRows.has(index);
          const detailsId = "batch-details-" + index;
          return <div className="batch-item" key={item.filename + index}>
            <div className="batch-row">
              <span>{item.filename}</span>
              {item.result ? <Status status={item.result.overall_status} /> : <span className="status missing">! Error</span>}
              <span>{item.error ?? String(issues.length) + " field(s) need attention"}{hasDetails ? <button className="batch-details-toggle" type="button" aria-expanded={expanded} aria-controls={detailsId} onClick={() => toggleBatchRow(index)}>{expanded ? "Hide details" : "View details"}</button> : null}</span>
            </div>
            {expanded ? <div className="batch-detail-panel" id={detailsId}>
              {item.error ? <p className="batch-error">{item.error}</p> : issues.map((field) => <article className="batch-field-detail" key={field.field}>
                <div><h3>{labels[field.field] ?? field.field}</h3><p>{field.reason}</p></div>
                <Status status={field.status} />
                <dl><div><dt>Application</dt><dd>{field.expected}</dd></div><div><dt>Label</dt><dd>{field.observed ?? "Not found"}</dd></div></dl>
              </article>)}
            </div> : null}
          </div>;
        })}
      </div>
    </section> : null}
    {result ? <section className="results" aria-live="polite"><div className={["summary", result.overall_status].join(" ")}><h2>{heading}</h2><p>Analysis completed in {(result.processing_ms / 1000).toFixed(1)} seconds.</p></div><h2>Verification results</h2><div className="rows">{result.fields.map((field) => <article className="result-row" key={field.field}><div><h3>{labels[field.field] ?? field.field}</h3><p>{field.reason}</p></div><Status status={field.status} /><dl><div><dt>Application</dt><dd>{field.expected}</dd></div><div><dt>Label</dt><dd>{field.observed ?? "Not found"}</dd></div></dl></article>)}</div><aside><h2>Manual warning check</h2><p>Confirm the warning heading is bold, the body is not bold, the type size is adequate, and the warning is separate from other information. OCR cannot verify these details.</p></aside><details><summary>View OCR text and prototype limitations</summary><pre>{result.ocr_text}</pre>{result.limitations.map((limitation) => <p key={limitation}>{limitation}</p>)}</details></section> : null}
  </main>;
}
