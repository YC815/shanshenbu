/** 核彈、預警、爆炸的繪製。全部用 Canvas path，不用 emoji。 */

/**
 * 畫一顆核彈。(x, y) 是彈體中心，angle 是飛行方向（彈頭朝向），r 是基準尺寸。
 * hot = 判定窗內，外圈泛紅光。
 */
export function drawBomb(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  r: number,
  angle: number,
  now: number,
  hot: boolean,
) {
  const L = r * 3.4; // 彈體長
  const R = r * 0.72; // 彈體半徑
  const tail = -L / 2;
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(angle);

  drawTrail(ctx, tail, R, r, now);

  // 尾翼
  ctx.fillStyle = '#2a2f37';
  for (const sgn of [-1, 1]) {
    ctx.beginPath();
    ctx.moveTo(tail + R * 0.6, sgn * R * 0.8);
    ctx.lineTo(tail - R * 0.5, sgn * R * 1.75);
    ctx.lineTo(tail - R * 0.75, sgn * R * 1.75);
    ctx.lineTo(tail - R * 0.35, sgn * R * 0.5);
    ctx.closePath();
    ctx.fill();
  }
  ctx.fillRect(tail - R * 0.75, -R * 0.12, R * 1.2, R * 0.24); // 中間那片側面看是一條線

  // 彈體：圓柱 + 尖頭
  const body = new Path2D();
  body.moveTo(tail, -R * 0.85);
  body.lineTo(L * 0.18, -R);
  body.bezierCurveTo(L * 0.42, -R, L * 0.5, -R * 0.35, L * 0.5, 0);
  body.bezierCurveTo(L * 0.5, R * 0.35, L * 0.42, R, L * 0.18, R);
  body.lineTo(tail, R * 0.85);
  body.closePath();

  if (hot) {
    ctx.shadowColor = `rgba(255,60,40,${0.6 + 0.4 * Math.sin(now / 70)})`;
    ctx.shadowBlur = r * 1.2;
  }
  const metal = ctx.createLinearGradient(0, -R, 0, R);
  metal.addColorStop(0, '#59616c');
  metal.addColorStop(0.25, '#d5dbe3');
  metal.addColorStop(0.45, '#8a929d');
  metal.addColorStop(1, '#262a31');
  ctx.fillStyle = metal;
  ctx.fill(body);
  ctx.shadowBlur = 0;

  ctx.save();
  ctx.clip(body);
  // 彈頭深色鼻錐
  ctx.fillStyle = 'rgba(30,34,40,0.75)';
  ctx.fillRect(L * 0.36, -R, L * 0.2, R * 2);
  // 尾端黃黑警示帶
  const bandX = tail + L * 0.06;
  const bandW = L * 0.12;
  ctx.fillStyle = '#e8b81c';
  ctx.fillRect(bandX, -R, bandW, R * 2);
  ctx.fillStyle = '#16181c';
  const stripe = bandW / 3;
  for (let i = -6; i < 6; i++) {
    ctx.beginPath();
    const sx = bandX + i * stripe * 2;
    ctx.moveTo(sx, R);
    ctx.lineTo(sx + stripe, R);
    ctx.lineTo(sx + stripe + R * 2 * 0.5, -R);
    ctx.lineTo(sx + R * 2 * 0.5, -R);
    ctx.closePath();
    ctx.fill();
  }
  // 鉚接縫
  ctx.strokeStyle = 'rgba(0,0,0,0.45)';
  ctx.lineWidth = Math.max(1, r * 0.05);
  for (const sx of [tail + L * 0.25, L * 0.18]) {
    ctx.beginPath();
    ctx.moveTo(sx, -R);
    ctx.lineTo(sx, R);
    ctx.stroke();
  }
  ctx.restore();

  ctx.strokeStyle = 'rgba(0,0,0,0.6)';
  ctx.lineWidth = Math.max(1, r * 0.04);
  ctx.stroke(body);

  // 輻射標誌（彈體正中）
  drawTrefoil(ctx, -L * 0.04, 0, R * 0.62);
  ctx.restore();
}

/** 輻射三葉標誌 */
function drawTrefoil(ctx: CanvasRenderingContext2D, x: number, y: number, s: number) {
  ctx.fillStyle = '#f2c21b';
  ctx.beginPath();
  ctx.arc(x, y, s, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = '#121316';
  for (let i = 0; i < 3; i++) {
    const a0 = -Math.PI / 2 + (i * 2 * Math.PI) / 3 - Math.PI / 6;
    ctx.beginPath();
    ctx.moveTo(x + Math.cos(a0) * s * 0.28, y + Math.sin(a0) * s * 0.28);
    ctx.arc(x, y, s * 0.88, a0, a0 + Math.PI / 3);
    ctx.arc(x, y, s * 0.28, a0 + Math.PI / 3, a0, true);
    ctx.closePath();
    ctx.fill();
  }
  ctx.beginPath();
  ctx.arc(x, y, s * 0.17, 0, Math.PI * 2);
  ctx.fill();
}

/** 尾焰 + 煙霧 */
function drawTrail(ctx: CanvasRenderingContext2D, tail: number, R: number, r: number, now: number) {
  for (let i = 7; i >= 1; i--) {
    const jitter = Math.sin(now / 90 + i * 1.7) * R * 0.25;
    const cx = tail - R * 0.8 - i * r * 0.7;
    const rad = R * (0.55 + i * 0.16);
    ctx.fillStyle = `rgba(150,150,155,${0.32 - i * 0.035})`;
    ctx.beginPath();
    ctx.arc(cx, jitter, rad, 0, Math.PI * 2);
    ctx.fill();
  }
  const flick = 1 + 0.25 * Math.sin(now / 35);
  const len = R * 2.4 * flick;
  const g = ctx.createLinearGradient(tail, 0, tail - len, 0);
  g.addColorStop(0, 'rgba(255,255,220,0.95)');
  g.addColorStop(0.3, 'rgba(255,190,60,0.9)');
  g.addColorStop(0.7, 'rgba(255,90,20,0.6)');
  g.addColorStop(1, 'rgba(255,60,0,0)');
  ctx.fillStyle = g;
  ctx.beginPath();
  ctx.moveTo(tail, -R * 0.55);
  ctx.quadraticCurveTo(tail - len * 0.6, -R * 0.5, tail - len, 0);
  ctx.quadraticCurveTo(tail - len * 0.6, R * 0.5, tail, R * 0.55);
  ctx.closePath();
  ctx.fill();
}

/** 預警：紅色虛線彈道 + 三角警示牌 */
export function drawWarning(
  ctx: CanvasRenderingContext2D,
  from: { x: number; y: number },
  to: { x: number; y: number },
  size: number,
  now: number,
) {
  const blink = Math.floor(now / 150) % 2 === 0;
  ctx.save();
  ctx.strokeStyle = `rgba(255,50,40,${blink ? 0.85 : 0.4})`;
  ctx.lineWidth = Math.max(2, size * 0.08);
  ctx.setLineDash([size * 0.4, size * 0.3]);
  ctx.lineDashOffset = -now / 20;
  ctx.beginPath();
  ctx.moveTo(from.x, from.y);
  ctx.lineTo(to.x, to.y);
  ctx.stroke();
  ctx.setLineDash([]);

  // 準星
  ctx.beginPath();
  ctx.arc(to.x, to.y, size * 0.9, 0, Math.PI * 2);
  ctx.moveTo(to.x - size * 1.3, to.y);
  ctx.lineTo(to.x + size * 1.3, to.y);
  ctx.moveTo(to.x, to.y - size * 1.3);
  ctx.lineTo(to.x, to.y + size * 1.3);
  ctx.stroke();

  if (blink) {
    const h = size * 1.6;
    const cx = from.x;
    const cy = from.y;
    ctx.fillStyle = '#ffcc00';
    ctx.strokeStyle = '#1a1a1a';
    ctx.lineWidth = Math.max(2, size * 0.1);
    ctx.lineJoin = 'round';
    ctx.beginPath();
    ctx.moveTo(cx, cy - h * 0.6);
    ctx.lineTo(cx + h * 0.62, cy + h * 0.45);
    ctx.lineTo(cx - h * 0.62, cy + h * 0.45);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = '#1a1a1a';
    ctx.fillRect(cx - h * 0.06, cy - h * 0.28, h * 0.12, h * 0.42);
    ctx.fillRect(cx - h * 0.06, cy + h * 0.2, h * 0.12, h * 0.12);
  }
  ctx.restore();
}

/** 被炸：火球 + 衝擊波環。k = 0..1 爆炸進度 */
export function drawExplosion(ctx: CanvasRenderingContext2D, x: number, y: number, r: number, k: number) {
  const a = 1 - k;
  const rad = r * (1.5 + 4 * Math.sqrt(k));
  const g = ctx.createRadialGradient(x, y, 0, x, y, rad);
  g.addColorStop(0, `rgba(255,255,235,${a})`);
  g.addColorStop(0.25, `rgba(255,220,90,${a})`);
  g.addColorStop(0.55, `rgba(255,110,20,${0.9 * a})`);
  g.addColorStop(0.8, `rgba(120,40,20,${0.6 * a})`);
  g.addColorStop(1, 'rgba(40,30,30,0)');
  ctx.fillStyle = g;
  ctx.beginPath();
  ctx.arc(x, y, rad, 0, Math.PI * 2);
  ctx.fill();

  ctx.strokeStyle = `rgba(255,240,200,${0.7 * a})`;
  ctx.lineWidth = r * 0.25 * a + 1;
  ctx.beginPath();
  ctx.arc(x, y, r * (2 + 9 * k), 0, Math.PI * 2);
  ctx.stroke();
}
