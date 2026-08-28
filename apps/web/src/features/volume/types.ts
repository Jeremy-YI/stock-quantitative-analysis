/** 与后端 apps/api/src/schemas/indicator.py 对齐的量能契约类型。 */

export interface VolumePoint {
  date: string
  close: number
  volume: number
  mavol1: number
  mavol2: number
  volume_ratio: number
  relation: string
}

export interface VolumeBody {
  symbol: string
  series: VolumePoint[]
}
