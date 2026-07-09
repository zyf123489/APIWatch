import * as fs from 'node:fs/promises';
import type { Dirent } from 'node:fs';
import * as path from 'node:path';

export type FrameworkId = 'fastapi' | 'litestar' | 'flask' | 'django';

export interface DetectedFramework {
  id: FrameworkId;
  label: string;
  reason: string;
}

const LABELS: Record<FrameworkId, string> = {
  fastapi: 'FastAPI',
  litestar: 'Litestar',
  flask: 'Flask',
  django: 'Django'
};

const MARKERS: Record<FrameworkId, RegExp[]> = {
  fastapi: [/\bfastapi\b/i, /from\s+fastapi\s+import/i],
  litestar: [/\blitestar\b/i, /from\s+litestar\s+import/i],
  flask: [/\bflask\b/i, /from\s+flask\s+import/i],
  django: [/\bdjango\b/i, /DJANGO_SETTINGS_MODULE/i]
};

const FILE_CANDIDATES = [
  'pyproject.toml',
  'requirements.txt',
  'requirements-dev.txt',
  'Pipfile',
  'poetry.lock',
  'manage.py'
];

export async function detectFrameworks(workspaceRoot: string): Promise<DetectedFramework[]> {
  const hits = new Map<FrameworkId, string>();

  for (const file of FILE_CANDIDATES) {
    await scanFile(path.join(workspaceRoot, file), file, hits);
  }

  await scanPythonFiles(workspaceRoot, hits);

  return (Object.keys(LABELS) as FrameworkId[])
    .filter((id) => hits.has(id))
    .map((id) => ({ id, label: LABELS[id], reason: hits.get(id) ?? 'Detected marker' }));
}

async function scanFile(filePath: string, displayName: string, hits: Map<FrameworkId, string>): Promise<void> {
  try {
    const stat = await fs.stat(filePath);
    if (!stat.isFile() || stat.size > 1024 * 1024) {
      return;
    }
    const text = await fs.readFile(filePath, 'utf8');
    recordHits(text, displayName, hits);
  } catch {
    // Missing or unreadable files are not detection failures.
  }
}

async function scanPythonFiles(root: string, hits: Map<FrameworkId, string>): Promise<void> {
  const queue = [root];
  let scanned = 0;
  while (queue.length && scanned < 200) {
    const dir = queue.shift()!;
    let entries: Dirent<string>[];
    try {
      entries = await fs.readdir(dir, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const entry of entries) {
      if (entry.name.startsWith('.') || ['node_modules', '__pycache__', '.venv', 'venv'].includes(entry.name)) {
        continue;
      }
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        queue.push(full);
      } else if (entry.isFile() && entry.name.endsWith('.py')) {
        scanned += 1;
        await scanFile(full, path.relative(root, full), hits);
        if (hits.size === Object.keys(LABELS).length) {
          return;
        }
      }
    }
  }
}

function recordHits(text: string, source: string, hits: Map<FrameworkId, string>): void {
  for (const id of Object.keys(MARKERS) as FrameworkId[]) {
    if (!hits.has(id) && MARKERS[id].some((pattern) => pattern.test(text))) {
      hits.set(id, `${LABELS[id]} marker in ${source}`);
    }
  }
}
