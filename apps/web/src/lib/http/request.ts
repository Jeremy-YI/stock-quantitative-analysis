/**
 * 前端 HTTP 封装 —— Go 风格 [err, res] 元组，不 throw。
 *
 * 调用方通过解构判断成败，而不是 try/catch：
 *   const [err, res] = await get<ApiResponse<MacdBody>>('/indicators/macd?...')
 *   if (err || !res) { ... } else { ... }
 */

export type HttpError = unknown

export type HttpResult<T> = [null, T] | [HttpError, undefined]

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? '/api/v1'

async function request<T>(path: string, init?: RequestInit): Promise<HttpResult<T>> {
  try {
    const res = await fetch(`${BASE_URL}${path}`, init)
    if (!res.ok) {
      // 后端错误响应统一是 { message }，尽量把语义串抛给调用方
      const body = (await res.json().catch(() => ({}))) as { message?: string; detail?: string }
      return [new Error(body.message ?? body.detail ?? `HTTP ${res.status}`), undefined]
    }
    const data = (await res.json()) as T
    return [null, data]
  } catch (err) {
    return [err, undefined]
  }
}

export function get<T>(path: string): Promise<HttpResult<T>> {
  return request<T>(path)
}

export function post<T>(path: string, body?: unknown): Promise<HttpResult<T>> {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}
