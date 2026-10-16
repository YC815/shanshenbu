/** 共用的小繪圖工具：文字、進度條、火柴人。 */

export function text(
  ctx: CanvasRenderingContext2D,
  str: string,
  x: number,
  y: number,
  size: number,
  color: string,
  align: CanvasTextAlign = 'center',
) {
  ctx.font = `bold ${size}px sans-serif`;
  ctx.textAlign = align;
  ctx.fillStyle = color;
  ctx.fillText(str, x, y);
}

export function bar(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, k: number, color: string) {
  ctx.fillStyle = '#222838';
  ctx.fillRect(x, y, w, h);
  ctx.fillStyle = color;
  ctx.fillRect(x, y, w * Math.max(0, Math.min(1, k)), h);
}

/**
 * 火柴人。(x, footY) 是腳底中心，h 是身高（像素）。
 * wob：哆嗦毛的晃動量（像素）；armsUp：雙手舉過頭頂。
 */
export function drawStick(
  ctx: CanvasRenderingContext2D,
  x: number,
  footY: number,
  h: number,
  { wob = 0, armsUp = false, color = '#e8eefc' }: { wob?: number; armsUp?: boolean; color?: string } = {},
) {
  const headR = h * 0.08;
  const hipY = footY - h * 0.45;
  const shoulderY = footY - h * 0.78;
  ctx.strokeStyle = color;
  ctx.lineWidth = Math.max(2, h * 0.035);
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  ctx.beginPath();
  // 腿
  ctx.moveTo(x - h * 0.1, footY);
  ctx.lineTo(x, hipY);
  ctx.lineTo(x + h * 0.1, footY);
  // 身體
  ctx.moveTo(x, hipY);
  ctx.lineTo(x + wob, shoulderY);
  // 手
  const handY = armsUp ? shoulderY - h * 0.3 : shoulderY + h * 0.25;
  ctx.moveTo(x - h * 0.18, handY + wob);
  ctx.lineTo(x + wob, shoulderY);
  ctx.lineTo(x + h * 0.18 + 2 * wob, handY - wob);
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(x + wob, shoulderY - headR * 1.4, headR, 0, Math.PI * 2);
  ctx.stroke();
}
