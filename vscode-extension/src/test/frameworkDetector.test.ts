import test from 'node:test';
import * as assert from 'node:assert/strict';
import * as fs from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';
import { detectFrameworks } from '../frameworkDetector';

test('detects django from manage.py', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'apiwatch-django-'));
  await fs.writeFile(path.join(root, 'manage.py'), 'import django\n');

  const result = await detectFrameworks(root);

  assert.equal(result.some((item) => item.id === 'django'), true);
});

test('detects fastapi and flask from source files', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'apiwatch-py-'));
  await fs.writeFile(path.join(root, 'app.py'), 'from fastapi import FastAPI\nfrom flask import Flask\n');

  const result = await detectFrameworks(root);
  const ids = result.map((item) => item.id);

  assert.deepEqual(ids.sort(), ['fastapi', 'flask']);
});

test('returns empty list for unknown project', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'apiwatch-empty-'));

  const result = await detectFrameworks(root);

  assert.deepEqual(result, []);
});
