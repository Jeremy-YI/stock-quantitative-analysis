/**
 * 策略回测评级 → 展示口径。
 *
 * 规则（scripts/build_strategy_ratings.py 机械判定，来源是四段样本外回测）：
 *   robust        四段全正            → 可推荐
 *   oos_positive  样本外三段全正        → 可推荐（弱）
 *   regime        有正有负（环境依赖）   → 仅内部
 *   insufficient  样本量不足           → 仅内部
 *   no_edge       无区分度 / 选择性过高  → 禁用
 *   overfit       样本内正、样本外全负   → 禁用
 */
import type { Tone } from '@/design'

export interface RatingMeta {
  label: string
  tone: Tone
  clientSafe: boolean
  hint: string
}

export const RATING_META: Record<string, RatingMeta> = {
  robust: { label: '回测稳健', tone: 'up', clientSafe: true, hint: '四段样本全正超额' },
  oos_positive: {
    label: '样本外为正',
    tone: 'accent',
    clientSafe: true,
    hint: '样本外三段全正，样本内为负，属弱有效',
  },
  regime: { label: '环境依赖', tone: 'warn', clientSafe: false, hint: '四段有正有负，仅内部参考' },
  insufficient: {
    label: '样本不足',
    tone: 'warn',
    clientSafe: false,
    hint: '某段样本量低于 100，无法定论',
  },
  no_edge: { label: '无区分度', tone: 'danger', clientSafe: false, hint: '幅度≈0 或选择性过高' },
  overfit: { label: '过拟合', tone: 'danger', clientSafe: false, hint: '样本内正、样本外全负' },
  unknown: { label: '未回测', tone: 'neutral', clientSafe: false, hint: '没有回测记录，不予推荐' },
}

export function ratingMeta(rating: string): RatingMeta {
  return RATING_META[rating] ?? RATING_META.unknown
}
