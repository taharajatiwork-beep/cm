#!/usr/bin/env node
import path from "node:path";
import { loadReports, writeSynthesis } from "./lib/aggregateReports";

function main(): void {
  const runRoot = process.argv[2];
  if (!runRoot) {
    console.error("Usage: npm run synthetic:aggregate -- <reports-run-directory>");
    process.exit(1);
  }
  const reports = loadReports(path.resolve(runRoot));
  if (!reports.length) {
    console.error("No report.json found in subfolders.");
    process.exit(1);
  }
  const outPath = writeSynthesis(runRoot, reports);
  console.log(`Wrote ${outPath}`);
}

main();
