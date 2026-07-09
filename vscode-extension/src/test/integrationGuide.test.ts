import test from 'node:test';
import * as assert from 'node:assert/strict';
import { guideFor } from '../integrationGuide';

test('renders fallback guide for unknown framework', () => {
  const guide = guideFor([]);

  assert.match(guide, /No supported Python web framework/);
  assert.match(guide, /apiwatch start/);
});

test('renders framework-specific snippets', () => {
  const guide = guideFor([
    { id: 'fastapi', label: 'FastAPI', reason: 'test' },
    { id: 'django', label: 'Django', reason: 'test' }
  ]);

  assert.match(guide, /ApiWatchASGIMiddleware/);
  assert.match(guide, /ApiWatchDjangoMiddleware/);
});
