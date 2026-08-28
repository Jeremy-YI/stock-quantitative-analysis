import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

/**
 * 合并 className：clsx 负责拼接 + 条件判断，tailwind-merge 负责去重冲突的
 * Tailwind 类（后写的覆盖先写的），避免「两个 bg-* 同时存在」的问题。
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
