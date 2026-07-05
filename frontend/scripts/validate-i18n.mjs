#!/usr/bin/env node
// Build-time i18n key validator — Changeset C06 §3 (Spec D08 §5.5 enforcement).
//
// Walks src/ for t('static.key') calls and verifies every key exists in both
// locale bundles. Keys built dynamically — t(variable), t('prefix.' + x),
// t(`template.${x}`) — cannot be resolved statically and are skipped rather
// than flagged; runtime still falls back to the raw-key display for those.

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = fileURLToPath(new URL('.', import.meta.url));
const SRC_DIR = join(__dirname, '..', 'src');
const LOCALES = {
  es: join(__dirname, '..', 'src', 'i18n', 'locales', 'es.json'),
  en: join(__dirname, '..', 'src', 'i18n', 'locales', 'en.json'),
};

// Matches t('key') / t("key") / t('key', {...}) / t('key').replace(...) —
// requires the closing quote to be immediately followed by ',' or ')', which
// excludes concatenation like t('prefix.' + x).
const T_CALL_RE = /\bt\(\s*(['"])((?:(?!\1)[^\\]|\\.)*)\1\s*[,)]/g;

function walk(dir, files = []) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) walk(full, files);
    else if (entry.endsWith('.ts')) files.push(full);
  }
  return files;
}

function extractUsages(files) {
  const usages = new Map(); // key -> Set of "file:line"
  for (const file of files) {
    const content = readFileSync(file, 'utf8');
    T_CALL_RE.lastIndex = 0;
    let match;
    while ((match = T_CALL_RE.exec(content))) {
      const key = match[2];
      const line = content.slice(0, match.index).split('\n').length;
      const loc = `${relative(process.cwd(), file)}:${line}`;
      if (!usages.has(key)) usages.set(key, new Set());
      usages.get(key).add(loc);
    }
  }
  return usages;
}

function main() {
  const usages = extractUsages(walk(SRC_DIR));

  const bundles = {};
  for (const [lang, path] of Object.entries(LOCALES)) {
    bundles[lang] = JSON.parse(readFileSync(path, 'utf8'));
  }

  const missing = [];
  for (const [key, locations] of usages) {
    for (const lang of Object.keys(bundles)) {
      if (!(key in bundles[lang])) {
        missing.push({ key, lang, locations: [...locations] });
      }
    }
  }

  if (missing.length > 0) {
    console.error(`\ni18n validation failed: ${missing.length} key reference(s) missing from a locale bundle.\n`);
    for (const { key, lang, locations } of missing) {
      console.error(`  Missing "${key}" in ${lang}.json`);
      for (const loc of locations) console.error(`    referenced at ${loc}`);
    }
    console.error('');
    process.exit(1);
  }

  console.log(`i18n validation passed: ${usages.size} static key(s) checked against ${Object.keys(bundles).length} locale bundle(s).`);
}

main();
