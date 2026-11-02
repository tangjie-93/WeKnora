import assert from 'node:assert/strict'
import { build } from 'esbuild'

const result = await build({
  entryPoints: ['src/api.ts'], bundle: true, write: false, format: 'esm',
  plugins: [{ name: 'auth-fixture', setup(builder) {
    builder.onResolve({ filter: /^\.\/auth$/ }, () => ({ path: 'auth', namespace: 'fixture' }))
    builder.onLoad({ filter: /.*/, namespace: 'fixture' }, () => ({
      contents: 'export const auth = {}; export function clearAuth() {} export function saveAuth() {}',
    }))
  } }],
})
const { api, streamChat } = await import(`data:text/javascript;base64,${Buffer.from(result.outputFiles[0].text).toString('base64')}`)
let xhr
globalThis.XMLHttpRequest = class {
  upload = {}
  constructor() { xhr = this }
  open() {}
  setRequestHeader() {}
  send() {}
}
const file = new Blob(['example'])
const progress = []
const success = api.uploadKnowledge('kb', file, percent => progress.push(percent))
xhr.upload.onprogress({ lengthComputable: true, loaded: 5, total: 10 })
assert.deepEqual(progress, [50])
xhr.status = 201
xhr.responseText = JSON.stringify({ success: true, data: { id: 'doc', parse_status: 'completed' } })
await xhr.onload()
assert.equal((await success).id, 'doc')
for (const body of ['Internal Server Error', '{"success":false,"error":{"message":"模型未配置"}}']) {
  const failure = api.uploadKnowledge('kb', file)
  xhr.status = 500
  xhr.responseText = body
  const rejected = assert.rejects(failure, /上传失败|模型未配置/)
  await xhr.onload()
  await rejected
}
const disconnected = api.uploadKnowledge('kb', file)
const rejected = assert.rejects(disconnected, /上传失败/)
xhr.onerror()
await rejected
console.log('Upload checks passed: progress, success, JSON/non-JSON errors, network failure')

const encoder = new TextEncoder()
function respond(events) {
  globalThis.fetch = async () => new Response(new ReadableStream({
    start(controller) {
      for (const event of events) {
        const bytes = encoder.encode(`data: ${JSON.stringify(event)}\n\n`)
        controller.enqueue(bytes.slice(0, 7))
        controller.enqueue(bytes.slice(7))
      }
      controller.close()
    },
  }), { status: 200 })
}
for (const content of ['第一轮答案', '第二轮答案']) {
  respond([{ response_type: 'answer', data: { content } }, { response_type: 'complete', data: {} }])
  let answer = ''
  await streamChat('same-session', '提问', event => {
    if (event.response_type === 'answer') answer += event.data.content
  })
  assert.equal(answer, content)
}
respond([{ response_type: 'error', data: { message: '模型调用失败' } }])
await assert.rejects(streamChat('same-session', '提问', () => {}), /模型调用失败/)
respond([{ response_type: 'answer', data: { content: '部分答案' } }])
await assert.rejects(streamChat('same-session', '提问', () => {}), /提前中断/)
console.log('Chat checks passed: two rounds, fragmented events, server errors, interrupted stream')
