/** 与后端 apps/api/src/schemas/common.py 对齐的统一响应包装。 */

export interface ApiResponse<T> {
  message: string
  body: T | null
}
