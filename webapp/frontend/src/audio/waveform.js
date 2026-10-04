/**
 * 録音中の波形（周波数バー）の描画（#11）
 * 設定画面と録音ツールで同じ見た目にするため、描画処理をここにまとめる。
 */

const BACKGROUND = 'rgb(0, 0, 0)'
const IDLE_LINE = 'rgb(100, 50, 150)'

/** 録音していないときの表示（中央に 1 本の線）。 */
export function drawIdleWaveform(canvas) {
  const ctx = canvas?.getContext('2d')
  if (!ctx) return
  ctx.fillStyle = BACKGROUND
  ctx.fillRect(0, 0, canvas.width, canvas.height)
  ctx.strokeStyle = IDLE_LINE
  ctx.lineWidth = 2
  ctx.beginPath()
  ctx.moveTo(0, canvas.height / 2)
  ctx.lineTo(canvas.width, canvas.height / 2)
  ctx.stroke()
}

/**
 * 録音中の周波数バーを描き続ける。
 * @param {HTMLCanvasElement} canvas
 * @param {AnalyserNode} analyser
 * @returns {() => void} 描画を止める関数
 */
export function startLiveWaveform(canvas, analyser) {
  const ctx = canvas?.getContext('2d')
  if (!ctx) return () => {}

  const data = new Uint8Array(analyser.frequencyBinCount)
  const barWidth = (canvas.width / data.length) * 2.5
  let frameId = 0

  const draw = () => {
    frameId = requestAnimationFrame(draw)
    analyser.getByteFrequencyData(data)
    // 半透明で塗り重ねて、前のバーが残像として少し残るようにする
    ctx.fillStyle = 'rgba(0, 0, 0, 0.2)'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    let x = 0
    for (let i = 0; i < data.length && x < canvas.width; i++) {
      const height = data[i] / 2
      ctx.fillStyle = `rgb(${height + 100}, 50, 150)`
      ctx.fillRect(x, canvas.height - height, barWidth, height)
      x += barWidth + 1
    }
  }
  draw()
  return () => cancelAnimationFrame(frameId)
}
