function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

function optionalEnv(name: string, defaultValue: string = ''): string {
  return process.env[name] ?? defaultValue;
}

export const config = {
  app: {
    name: optionalEnv('APP_NAME', 'marlo-inbox'),
    baseUrl: optionalEnv('APP_BASE_URL', 'http://localhost:5173'),
  },
  openai: {
    apiKey: requireEnv('OPENAI_API_KEY'),
  },
  langsmith: {
    apiKey: optionalEnv('LANGSMITH_API_KEY'),
    project: optionalEnv('LANGSMITH_PROJECT', 'marlo-inbox'),
  },
} as const;
