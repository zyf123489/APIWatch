import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import * as http from 'node:http';
import type { ApiWatchConfig } from './config';
import { collectorBaseUrl } from './config';

export interface DoctorResult {
  ok: boolean;
  message: string;
  totalRequests?: number;
}

export class CollectorManager {
  private process: ChildProcessWithoutNullStreams | undefined;

  constructor(private readonly output: { appendLine(message: string): void }) {}

  get running(): boolean {
    return this.process !== undefined && this.process.exitCode === null;
  }

  async start(config: ApiWatchConfig): Promise<'started' | 'already-running'> {
    if (this.running || (await isCollectorReachable(config))) {
      return 'already-running';
    }

    const args = [
      '-m',
      'apiwatch_collector.cli',
      'start',
      '--host',
      config.collectorHost,
      '--port',
      String(config.collectorPort)
    ];
    if (config.collectorToken) {
      args.push('--token', config.collectorToken);
    }
    this.process = spawn(config.pythonExecutable, args, {
      cwd: process.cwd(),
      windowsHide: true
    });
    this.process.stdout.on('data', (data: Buffer) => this.output.appendLine(data.toString().trimEnd()));
    this.process.stderr.on('data', (data: Buffer) => this.output.appendLine(data.toString().trimEnd()));
    this.process.on('exit', (code) => {
      this.output.appendLine(`collector exited (${code ?? 'signal'})`);
      this.process = undefined;
    });
    return 'started';
  }

  stop(): boolean {
    if (!this.running || !this.process) {
      return false;
    }
    this.process.kill();
    this.process = undefined;
    return true;
  }
}

export async function doctor(config: Pick<ApiWatchConfig, 'collectorHost' | 'collectorPort' | 'collectorToken'>): Promise<DoctorResult> {
  try {
    const summary = await getJson<{ total_requests?: number }>(`${collectorBaseUrl(config)}/summary`, config.collectorToken);
    return {
      ok: true,
      message: `Collector OK at ${collectorBaseUrl(config)}`,
      totalRequests: Number(summary.total_requests ?? 0)
    };
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    return { ok: false, message: `Collector unavailable at ${collectorBaseUrl(config)}: ${detail}` };
  }
}

async function isCollectorReachable(config: Pick<ApiWatchConfig, 'collectorHost' | 'collectorPort' | 'collectorToken'>): Promise<boolean> {
  return (await doctor(config)).ok;
}

function getJson<T>(url: string, token = ''): Promise<T> {
  return new Promise((resolve, reject) => {
    const headers = token ? { Authorization: `Bearer ${token}` } : undefined;
    const req = http.get(url, { timeout: 1500, headers }, (res) => {
      if ((res.statusCode ?? 0) < 200 || (res.statusCode ?? 0) >= 300) {
        res.resume();
        reject(new Error(`HTTP ${res.statusCode}`));
        return;
      }
      let body = '';
      res.setEncoding('utf8');
      res.on('data', (chunk) => {
        body += chunk;
      });
      res.on('end', () => {
        try {
          resolve(JSON.parse(body) as T);
        } catch (error) {
          reject(error);
        }
      });
    });
    req.on('timeout', () => {
      req.destroy(new Error('timeout'));
    });
    req.on('error', reject);
  });
}
