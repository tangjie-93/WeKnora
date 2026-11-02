// 嵌入模式账号解析：优先从 URL 查询参数动态传入，其次环境变量，最后默认账号。
//
// 后续宿主系统接入时，通过 ?account=xxx&password=yyy 动态传入已登录用户的凭据，
// 即可在代码内自动登录，无需修改本文件。默认账号仅作为当前临时兜底。
export interface Credentials {
  account: string
  password: string
}

function queryValue(key: string): string {
  return new URLSearchParams(window.location.search).get(key) || ''
}

export function resolveCredentials(): Credentials {
  return {
    account:
      queryValue('account') ||
      import.meta.env.VITE_EMBED_ACCOUNT ||
      'tang.jie@ecar.com',
    password:
      queryValue('password') ||
      import.meta.env.VITE_EMBED_PASSWORD ||
      'Tj930210!',
  }
}
