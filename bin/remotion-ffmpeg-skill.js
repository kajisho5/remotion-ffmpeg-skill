#!/usr/bin/env node
/**
 * remotion-ffmpeg-skill installer.
 *
 * Copies SKILL.md, scripts/, templates/ and references/ into the skills directory of one or
 * more coding agents. Default target is Claude Code (~/.claude/skills/remotion-ffmpeg-skill).
 *
 *   npx remotion-ffmpeg-skill                 # Claude Code
 *   npx remotion-ffmpeg-skill --cursor        # Cursor  (~/.cursor/skills/remotion-ffmpeg-skill)
 *   npx remotion-ffmpeg-skill --codex         # Codex   (~/.agents/skills/remotion-ffmpeg-skill)
 *   npx remotion-ffmpeg-skill --all           # all of the above
 *   npx remotion-ffmpeg-skill --dir ./skills  # custom parent directory
 *   npx remotion-ffmpeg-skill --project       # ./.claude/skills/remotion-ffmpeg-skill
 *   npx remotion-ffmpeg-skill --uninstall     # remove from the selected targets
 *   npx remotion-ffmpeg-skill doctor          # what this machine can do
 *   npx remotion-ffmpeg-skill contract --json # machine-readable contract (tools, schemas, verification)
 *
 * This skill needs ffmpeg-skill next to it: `npx ffmpeg-skill` with the same target flags.
 */
'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const SKILL_NAME = 'remotion-ffmpeg-skill';
const ROOT = path.resolve(__dirname, '..');
const PAYLOAD = ['SKILL.md', 'scripts', 'templates', 'references', 'mcp', 'package.json', 'LICENSE'];

const args = process.argv.slice(2);
const has = (flag) => args.includes(flag);
const optValue = (flag) => {
  const i = args.indexOf(flag);
  return i !== -1 && args[i + 1] ? args[i + 1] : null;
};

if (has('--help') || has('-h')) {
  console.log(fs.readFileSync(__filename, 'utf8').split('*/')[0].replace(/^\/\*\*?\s?|^\s\*\s?/gm, ''));
  process.exit(0);
}

function python() {
  const candidates = process.platform === 'win32' ? ['python3', 'python', 'py'] : ['python3'];
  for (const c of candidates) {
    const r = spawnSync(c, ['-c', 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)']);
    if (!r.error && r.status === 0) return c;
  }
  return null;
}

if (args[0] === 'doctor' || args[0] === 'contract') {
  const py = python();
  if (!py) {
    console.error('Python 3.10+ not found on PATH.');
    process.exit(3);
  }
  const script = args[0] === 'doctor' ? 'doctor.py' : '_contract.py';
  const r = spawnSync(py, [path.join(ROOT, 'scripts', script), ...args.slice(1)], { stdio: 'inherit' });
  process.exit(r.status === null ? 1 : r.status);
}

const home = os.homedir();
const targets = [];
if (optValue('--dir')) targets.push(path.resolve(optValue('--dir')));
if (has('--project')) targets.push(path.resolve('.claude', 'skills'));
if (has('--cursor') || has('--all')) targets.push(path.join(home, '.cursor', 'skills'));
if (has('--codex') || has('--all')) targets.push(path.join(home, '.agents', 'skills'));
if (has('--all') || targets.length === 0) targets.unshift(path.join(home, '.claude', 'skills'));

function copy(src, dst) {
  const st = fs.statSync(src);
  if (st.isDirectory()) {
    if (['node_modules', '__pycache__', '.rfs'].includes(path.basename(src))) return;
    fs.mkdirSync(dst, { recursive: true });
    for (const e of fs.readdirSync(src)) copy(path.join(src, e), path.join(dst, e));
  } else {
    fs.copyFileSync(src, dst);
  }
}

for (const parent of [...new Set(targets)]) {
  const dest = path.join(parent, SKILL_NAME);
  if (has('--uninstall')) {
    fs.rmSync(dest, { recursive: true, force: true });
    console.log(`removed ${dest}`);
    continue;
  }
  fs.rmSync(dest, { recursive: true, force: true });
  fs.mkdirSync(dest, { recursive: true });
  for (const item of PAYLOAD) {
    const src = path.join(ROOT, item);
    if (fs.existsSync(src)) copy(src, path.join(dest, item));
  }
  console.log(`installed ${SKILL_NAME} -> ${dest}`);
  if (!fs.existsSync(path.join(parent, 'ffmpeg-skill', 'scripts', 'probe.py')) && !process.env.FFMPEG_SKILL_DIR) {
    console.log(`  note: ffmpeg-skill is not next to it yet. Install it too: npx ffmpeg-skill${parent.includes('.cursor') ? ' --cursor' : parent.includes('.agents') ? ' --codex' : ''}`);
  }
}
if (!python()) console.log('warning: Python 3.10+ not found on PATH; the scripts need it.');
