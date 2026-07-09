import type { DetectedFramework, FrameworkId } from './frameworkDetector';

const SNIPPETS: Record<FrameworkId, string> = {
  fastapi: `from apiwatch.integrations.asgi import ApiWatchASGIMiddleware

app.add_middleware(ApiWatchASGIMiddleware, project="demo", framework="fastapi")`,
  litestar: `from litestar.middleware import DefineMiddleware
from apiwatch.integrations.asgi import ApiWatchASGIMiddleware

middleware = [DefineMiddleware(ApiWatchASGIMiddleware, project="demo", framework="litestar")]`,
  flask: `from apiwatch.integrations.flask import ApiWatchFlask

ApiWatchFlask(app, project="demo")`,
  django: `# settings.py
MIDDLEWARE = [
    "apiwatch.integrations.django.ApiWatchDjangoMiddleware",
    # ...
]

APIWATCH_PROJECT = "demo"`
};

export function guideFor(frameworks: DetectedFramework[]): string {
  if (frameworks.length === 0) {
    return `# APIWatch Integration Guide

No supported Python web framework was detected.

Supported frameworks:
- FastAPI / Litestar via ASGI middleware
- Flask via ApiWatchFlask
- Django via ApiWatchDjangoMiddleware

Start collector:

\`\`\`bash
apiwatch start
\`\`\`
`;
  }

  const sections = frameworks.map((framework) => `## ${framework.label}

Detected: ${framework.reason}

\`\`\`python
${SNIPPETS[framework.id]}
\`\`\``);

  return `# APIWatch Integration Guide

Start collector:

\`\`\`bash
apiwatch start
\`\`\`

${sections.join('\n\n')}
`;
}
