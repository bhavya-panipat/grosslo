"use client";

import { useRef, useState } from "react";
import Papa from "papaparse";
import { AlertTriangle, FileSpreadsheet, Upload } from "lucide-react";
import CardShell from "@/components/card-shell";

type Props = {
  mode: "audit";
  onRowsParsed: (rows: Record<string, string>[]) => void;
};

const AUDIT_COLUMNS = [
  "name", "ctc", "basic", "hra", "lta", "special_allowance", "employer_pf",
  "employer_nps", "nps_opted", "rent_paid", "city", "band_min", "band_max",
];

const MODE_LABEL: Record<Props["mode"], string> = {
  audit: "Compliance & Savings Audit",
};

export default function CsvUploadCard({ mode, onRowsParsed }: Props) {
  const [fileName, setFileName] = useState<string | null>(null);
  const [rowCount, setRowCount] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [parsing, setParsing] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const expectedColumnList = AUDIT_COLUMNS;
  const expectedColumns = expectedColumnList.join(", ");

  const handleFile = (file: File) => {
    setParsing(true);
    setError(null);
    setFileName(file.name);
    Papa.parse<Record<string, string>>(file, {
      header: true,
      skipEmptyLines: true,
      complete: (results) => {
        setParsing(false);
        if (results.errors.length > 0) {
          setError(results.errors[0].message);
          setRowCount(null);
          return;
        }
        if (results.data.length === 0) {
          setError("No rows found in this file.");
          setRowCount(null);
          return;
        }
        // Catches a missing/misnamed column early — without this check the
        // request would still fire with silently-defaulted/missing fields
        // and look like the product is broken rather than the file being
        // wrong.
        const foundColumns = results.meta.fields ?? [];
        const missing = expectedColumnList.filter((c) => !foundColumns.includes(c));
        if (missing.length > 0) {
          setError(
            `This doesn't look like a ${MODE_LABEL[mode]} file — missing column${missing.length === 1 ? "" : "s"}: ${missing.join(", ")}. This page only audits existing structures — for a new hire, use the HR page instead. Or fix the CSV's header row.`,
          );
          setRowCount(null);
          return;
        }
        setRowCount(results.data.length);
        onRowsParsed(results.data);
      },
      error: (err) => {
        setParsing(false);
        setError(err.message);
        setRowCount(null);
      },
    });
  };

  return (
    <CardShell>
      <div className="flex items-center gap-2 text-neutral-300">
        <FileSpreadsheet className="h-4 w-4 text-gold-bright" />
        <h3 className="font-display text-lg font-semibold text-white">Upload CSV</h3>
      </div>
      <p className="mt-1 text-sm text-neutral-500">
        Expected columns: <span className="font-mono text-xs text-neutral-400">{expectedColumns}</span>
      </p>

      <label className="mt-4 flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-white/15 bg-black/30 px-6 py-8 text-center transition-colors hover:border-gold-bright/40 hover:bg-white/[0.02]">
        <Upload className="h-5 w-5 text-neutral-500" />
        <span className="text-sm text-neutral-400">
          {fileName ? fileName : "Click to choose a CSV file"}
        </span>
        <input
          ref={inputRef}
          type="file"
          accept=".csv,text/csv"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFile(file);
          }}
        />
      </label>

      {parsing && (
        <div className="mt-3 h-4 w-32 animate-pulse rounded bg-white/[0.04]" />
      )}
      {error && (
        <div className="mt-3 flex items-start gap-2 rounded-lg border border-red-400/20 bg-red-400/[0.05] p-3 text-xs text-red-300">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          {error}
        </div>
      )}
      {rowCount !== null && !error && (
        <p className="mt-3 text-xs text-emerald-300/80">
          Parsed {rowCount} row{rowCount === 1 ? "" : "s"}.
        </p>
      )}
    </CardShell>
  );
}
