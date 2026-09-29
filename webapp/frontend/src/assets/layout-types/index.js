import statementIcon from './statement.svg'
import listIcon from './list.svg'
import sequenceIcon from './sequence.svg'
import contrastIcon from './contrast.svg'
import hierarchyIcon from './hierarchy.svg'
import cycleIcon from './cycle.svg'
import matrixIcon from './matrix.svg'
import setsIcon from './sets.svg'
import tableIcon from './table.svg'
import chartIcon from './chart.svg'
import formulaIcon from './formula.svg'
import mediaIcon from './media.svg'
import dialogIcon from './dialog.svg'
import coverIcon from './cover.svg'
import defaultIcon from './default.svg'

/**
 * 14 種の情報の型 ID と SVG アイコン URL のマッピング。
 * 単色シルエット SVG で、CSS mask-image を通じて currentColor（アクティブ色など）に追従します。
 */
export const LAYOUT_TYPE_ICONS = {
  statement: statementIcon,
  list: listIcon,
  sequence: sequenceIcon,
  contrast: contrastIcon,
  hierarchy: hierarchyIcon,
  cycle: cycleIcon,
  matrix: matrixIcon,
  sets: setsIcon,
  table: tableIcon,
  chart: chartIcon,
  formula: formulaIcon,
  media: mediaIcon,
  dialog: dialogIcon,
  cover: coverIcon,
}

/**
 * 指定された型のアイコン URL を返します。
 * 未知の型やアイコンが未定義の場合は defaultIcon（フォールバック）を返します。
 *
 * @param {string} type - 情報の型 ID（例: 'sequence', 'contrast'）
 * @returns {string} アイコンの画像 URL
 */
export function getLayoutTypeIcon(type) {
  if (!type) return defaultIcon
  return LAYOUT_TYPE_ICONS[type] || defaultIcon
}
