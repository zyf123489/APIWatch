export interface ApiWatchConfig {
  collectorHost: string;
  collectorPort: number;
  collectorToken: string;
  pythonExecutable: string;
  openDashboardInWebview: boolean;
}

export function collectorBaseUrl(config: Pick<ApiWatchConfig, 'collectorHost' | 'collectorPort'>): string {
  return `http://${config.collectorHost}:${config.collectorPort}`;
}
