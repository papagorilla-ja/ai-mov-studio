import basicIcon from './basic.svg'
import colorsTypographyIcon from './colors_typography.svg'
import backgroundIcon from './background.svg'
import presentationIcon from './presentation.svg'
import motionSoundIcon from './motion_sound.svg'

/**
 * デザインスタイルのグループ ID と SVG アイコン URL のマッピング。
 * 単色シルエット SVG で、CSS mask-image を通じて currentColor（アクティブ色など）に追従します。
 */
export const STYLE_GROUP_ICONS = {
  basic: basicIcon,
  colors_typography: colorsTypographyIcon,
  background: backgroundIcon,
  presentation: presentationIcon,
  motion_sound: motionSoundIcon,
}

/**
 * 指定されたグループのアイコン URL を返します。
 *
 * @param {string} group - グループ ID（例: 'basic', 'colors_typography'）
 * @returns {string} アイコンの画像 URL
 */
export function getStyleGroupIcon(group) {
  return STYLE_GROUP_ICONS[group] || basicIcon
}
