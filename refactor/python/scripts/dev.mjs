import { spawn, spawnSync } from 'node:child_process';
import { existsSync, mkdirSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const workspaceDirectory = path.resolve(scriptDirectory, '..');

const backendDirectory = path.join(workspaceDirectory, 'backend');
const frontendDirectory = path.join(workspaceDirectory, 'frontend');
const authDirectory = path.join(backendDirectory, '.local', 'auth');
const authDatabase = path.join(authDirectory, 'auth.sqlite3');
const backendPort = process.env.BACKEND_PORT || '18080';
const frontendPort = process.env.FRONTEND_PORT || '15400';
const backendTarget = process.env.BACKEND_PROXY_TARGET || `http://127.0.0.1:${backendPort}`;

const commands = [
  {
    name: 'backend',
    command: 'uv',
    args: [
      'run',
      '--frozen',
      'uvicorn',
      'app.main:app',
      '--no-proxy-headers',
      '--host',
      '127.0.0.1',
      '--port',
      backendPort,
      '--reload',
    ],
    cwd: backendDirectory,
    env: { WEKNORA_AUTH_DB_PATH: authDatabase },
    port: backendPort,
  },
  {
    name: 'frontend',
    command: 'pnpm',
    args: ['dev', '--host', '127.0.0.1'],
    cwd: frontendDirectory,
    env: { FRONTEND_PORT: frontendPort, BACKEND_PROXY_TARGET: backendTarget },
    port: frontendPort,
  },
];

const childProcesses = new Map();
let shuttingDown = false;
let exitCode = 0;

function getListeningPids(port) {
  const result = spawnSync('lsof', ['-tiTCP:' + port, '-sTCP:LISTEN'], {
    encoding: 'utf8',
  });

  if (result.error) {
    throw new Error(`无法检查端口 ${port}: ${result.error.message}`);
  }
  if (result.status !== 0 && result.status !== 1) {
    throw new Error(`无法检查端口 ${port}: lsof exited with code ${result.status}`);
  }

  return result.stdout
    .split(/\s+/)
    .map((value) => Number.parseInt(value, 10))
    .filter((pid) => Number.isInteger(pid) && pid > 0 && pid !== process.pid);
}

function stopExistingProcessOnPort(port) {
  const pids = getListeningPids(port);

  for (const pid of pids) {
    console.log(`[launcher] stopping existing process ${pid} on port ${port}`);
    const killResult = spawnSync('kill', ['-TERM', String(pid)], { encoding: 'utf8' });
    if (killResult.error || killResult.status !== 0) {
      const reason = killResult.error?.message ?? `exit code ${killResult.status}`;
      throw new Error(`无法停止端口 ${port} 上的进程 ${pid}: ${reason}`);
    }
  }

  const deadline = Date.now() + 5000;
  while (getListeningPids(port).length > 0 && Date.now() < deadline) {
    spawnSync('sleep', ['0.1']);
  }

  if (getListeningPids(port).length > 0) {
    throw new Error(`端口 ${port} 在停止旧进程后仍被占用。`);
  }
}

function ensureAuthDatabase() {
  const secretPath = `${authDatabase}.jwt-secret`;
  if (existsSync(authDatabase) && existsSync(secretPath)) {
    return;
  }
  if (existsSync(authDatabase) || existsSync(secretPath)) {
    throw new Error('认证数据库或 JWT 密钥文件不完整，请修复 .local/auth 后重试。');
  }

  mkdirSync(authDirectory, { recursive: true, mode: 0o700 });
  console.log('[launcher] initializing local authentication database');
  const result = spawnSync(
    'uv',
    ['run', '--frozen', 'python', '-m', 'app.cli.init_auth_database', '--path', authDatabase],
    { cwd: backendDirectory, env: process.env, encoding: 'utf8', stdio: 'inherit' },
  );
  if (result.error || result.status !== 0) {
    const reason = result.error?.message ?? `exit code ${result.status}`;
    throw new Error(`认证数据库初始化失败: ${reason}`);
  }
}

function formatCommand(processDefinition) {
  return [processDefinition.command, ...processDefinition.args].join(' ');
}

function finishShutdown() {
  if (childProcesses.size === 0) {
    process.exit(exitCode);
  }
}

function shutdown(code) {
  if (!shuttingDown) {
    shuttingDown = true;
    exitCode = code;
  } else if (code !== 0) {
    exitCode = code;
  }

  for (const child of childProcesses.values()) {
    if (child.exitCode === null && !child.killed) {
      child.kill('SIGTERM');
    }
  }

  finishShutdown();
}

function startProcess(processDefinition) {
  console.log(`[${processDefinition.name}] starting: ${formatCommand(processDefinition)}`);
  const child = spawn(processDefinition.command, processDefinition.args, {
    cwd: processDefinition.cwd,
    env: { ...process.env, ...processDefinition.env },
    stdio: 'inherit',
  });

  childProcesses.set(processDefinition.name, child);

  child.on('error', (error) => {
    if (shuttingDown) {
      return;
    }

    console.error(`[${processDefinition.name}] failed to start: ${error.message}`);
    shutdown(1);
  });

  child.on('exit', (code, signal) => {
    childProcesses.delete(processDefinition.name);

    if (shuttingDown) {
      finishShutdown();
      return;
    }

    if (code !== 0) {
      exitCode = code ?? 1;
      console.error(
        `[${processDefinition.name}] exited unexpectedly with ${
          signal ? `signal ${signal}` : `code ${code}`
        }`,
      );
      shutdown(exitCode);
      return;
    }

    console.log(`[${processDefinition.name}] exited normally; stopping the other service.`);
    shutdown(0);
  });
}

process.on('SIGINT', () => {
  console.log('Stopping frontend and backend...');
  shutdown(0);
});

process.on('SIGTERM', () => {
  shutdown(0);
});

try {
  ensureAuthDatabase();
  for (const processDefinition of commands) {
    stopExistingProcessOnPort(processDefinition.port);
  }

  for (const processDefinition of commands) {
    startProcess(processDefinition);
  }
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  console.error(`Failed to start development services: ${message}`);
  shutdown(1);
}
