import * as vscode from 'vscode';
import { CollectorManager, doctor } from './collector';
import { collectorBaseUrl, type ApiWatchConfig } from './config';
import { detectFrameworks } from './frameworkDetector';
import { guideFor } from './integrationGuide';

let collectorManager: CollectorManager;

export function activate(context: vscode.ExtensionContext): void {
  const output = vscode.window.createOutputChannel('APIWatch');
  collectorManager = new CollectorManager(output);
  context.subscriptions.push(output);

  context.subscriptions.push(
    vscode.commands.registerCommand('apiwatch.startCollector', async () => {
      const result = await collectorManager.start(readConfig());
      if (result === 'already-running') {
        vscode.window.showInformationMessage('APIWatch collector is already running.');
      } else {
        output.show(true);
        vscode.window.showInformationMessage('APIWatch collector started.');
      }
    }),
    vscode.commands.registerCommand('apiwatch.stopCollector', () => {
      const stopped = collectorManager.stop();
      vscode.window.showInformationMessage(stopped ? 'APIWatch collector stopped.' : 'No APIWatch collector started by this extension.');
    }),
    vscode.commands.registerCommand('apiwatch.openDashboard', async () => {
      await openDashboard(readConfig(), context);
    }),
    vscode.commands.registerCommand('apiwatch.showIntegrationGuide', async () => {
      await showIntegrationGuide();
    }),
    vscode.commands.registerCommand('apiwatch.doctor', async () => {
      const result = await doctor(readConfig());
      const message = result.ok
        ? `${result.message}; requests=${result.totalRequests ?? 0}`
        : result.message;
      if (result.ok) {
        vscode.window.showInformationMessage(message);
      } else {
        vscode.window.showWarningMessage(message);
      }
    })
  );
}

export function deactivate(): void {
  collectorManager?.stop();
}

function readConfig(): ApiWatchConfig {
  const config = vscode.workspace.getConfiguration('apiwatch');
  return {
    collectorHost: config.get<string>('collectorHost', '127.0.0.1'),
    collectorPort: config.get<number>('collectorPort', 8765),
    pythonExecutable: config.get<string>('pythonExecutable', 'python'),
    openDashboardInWebview: config.get<boolean>('openDashboardInWebview', false)
  };
}

async function openDashboard(config: ApiWatchConfig, context: vscode.ExtensionContext): Promise<void> {
  const url = `${collectorBaseUrl(config)}/dashboard`;
  if (!config.openDashboardInWebview) {
    await vscode.env.openExternal(vscode.Uri.parse(url));
    return;
  }

  const panel = vscode.window.createWebviewPanel(
    'apiwatchDashboard',
    'APIWatch Dashboard',
    vscode.ViewColumn.One,
    { enableScripts: true }
  );
  panel.webview.html = dashboardHtml(panel.webview, context, url);
}

function dashboardHtml(webview: vscode.Webview, context: vscode.ExtensionContext, dashboardUrl: string): string {
  const nonce = String(Date.now());
  const csp = [
    `default-src 'none'`,
    `frame-src http://127.0.0.1:* http://localhost:*`,
    `style-src ${webview.cspSource} 'unsafe-inline'`,
    `script-src 'nonce-${nonce}'`
  ].join('; ');
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="Content-Security-Policy" content="${csp}">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>APIWatch</title>
  <style>html,body,iframe{width:100%;height:100%;margin:0;border:0}</style>
</head>
<body>
  <iframe src="${dashboardUrl}" title="APIWatch Dashboard"></iframe>
  <script nonce="${nonce}">console.log('APIWatch dashboard webview');</script>
</body>
</html>`;
}

async function showIntegrationGuide(): Promise<void> {
  const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  if (!root) {
    vscode.window.showWarningMessage('Open a workspace folder before generating an APIWatch integration guide.');
    return;
  }
  const frameworks = await detectFrameworks(root);
  const doc = await vscode.workspace.openTextDocument({
    language: 'markdown',
    content: guideFor(frameworks)
  });
  await vscode.window.showTextDocument(doc, vscode.ViewColumn.One);
}
