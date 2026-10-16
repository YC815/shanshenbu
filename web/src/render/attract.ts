/** 待機畫面：兩張動作示範卡輪播 + 「雙手舉過頭頂開始」進度圈。疊在即時影像上，中央留給玩家。 */
import { CONFIG as C } from '../game/config';
import type { Game } from '../game/game';
import type { SensorState } from '../types';
import { drawStick, text } from './draw';
import { drawBomb } from './nuke';

const DEMO_MS = 2600;
const PANEL = 'rgba(10,14,22,0.78)';

const clamp01 = (k: number) => Math.max(0, Math.min(1, k));
const ease = (k: number) => k * k * (3 - 2 * k);

export function drawAttract(
  ctx: CanvasRenderingContext2D,
  g: Game,
  s: SensorState,
  W: number,
  H: number,
  u: number,
  now: number,
) {
  text(ctx, '閃身步・核彈閃避', W / 2, 11 * u, 8 * u, '#ffffff');
  text(ctx, `閃過 ${C.WIN_DODGES} 顆獲勝・被炸 ${C.HP} 次出局`, W / 2, 17 * u, 3.2 * u, '#9fb3d9');

  const cw = Math.min(36 * u, W * 0.26);
  demoCard(ctx, 3 * u, 24 * u, cw, 50 * u, u, now, 'side');
  demoCard(ctx, W - 3 * u - cw, 24 * u, cw, 50 * u, u, now, 'top');
  drawStart(ctx, g, s, W, u, now);
}

function demoCard(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  u: number,
  now: number,
  kind: 'side' | 'top',
) {
  ctx.fillStyle = PANEL;
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, 2 * u);
  ctx.fill();
  text(ctx, kind === 'side' ? '核彈從旁邊飛來' : '核彈從頭上掉下來', x + w / 2, y + 6 * u, 3.4 * u, '#ffffff');

  // 動畫區
  const ay = y + 9 * u;
  const ah = h - 22 * u;
  ctx.save();
  ctx.beginPath();
  ctx.rect(x, ay, w, ah);
  ctx.clip();
  const k = (now % DEMO_MS) / DEMO_MS;
  const footY = ay + ah * 0.95;
  const fh = ah * 0.62;
  const cx = x + w / 2;
  const r = fh * 0.07;
  let dodgedAt: number;
  if (kind === 'side') {
    // 先往旁邊跨，核彈從原本的位置穿過去
    drawStick(ctx, cx + ease(clamp01((k - 0.2) / 0.15)) * w * 0.28, footY, fh);
    const p = clamp01(k / 0.75);
    if (p < 1) drawBomb(ctx, x - w * 0.15 + w * 1.3 * p, footY - fh * 0.7, r, 0, now, k > 0.2);
    dodgedAt = 0.4;
  } else {
    // 用力抖，核彈被彈開
    const shaking = k > 0.12 && k < 0.7;
    drawStick(ctx, cx, footY, fh, { wob: shaking ? Math.sin(now / 30) * fh * 0.06 : 0 });
    const stopY = footY - fh * 1.15;
    const startY = ay - r * 3;
    if (k < 0.55) {
      drawBomb(ctx, cx, startY + (stopY - startY) * (k / 0.55), r, Math.PI / 2, now, k > 0.2);
    } else if (k < 0.85) {
      const p = (k - 0.55) / 0.3;
      drawBomb(ctx, cx + p * w * 0.6, stopY - Math.sin(p * Math.PI) * fh * 0.3, r, Math.PI / 2 + p * 4, now, false);
    }
    dodgedAt = 0.55;
  }
  if (k > dodgedAt && k < 0.95) text(ctx, '閃過！', cx, ay + ah * 0.18, 4 * u, '#50ff8c');
  ctx.restore();

  text(ctx, kind === 'side' ? '閃身步' : '狗熊哆嗦毛', x + w / 2, y + h - 8.5 * u, 4.4 * u, '#ffd23f');
  text(ctx, kind === 'side' ? '往旁邊跨一大步' : '全身用力抖起來', x + w / 2, y + h - 3.5 * u, 3 * u, '#e8eefc');
}

/** 舉手開局：火柴人圖示外圈是進度 */
function drawStart(ctx: CanvasRenderingContext2D, g: Game, s: SensorState, W: number, u: number, now: number) {
  const cx = W / 2;
  const cy = 70 * u;
  const R = 7 * u;
  const p = g.startHold / C.START_HOLD_S;

  ctx.fillStyle = PANEL;
  ctx.beginPath();
  ctx.arc(cx, cy, R * 1.3, 0, Math.PI * 2);
  ctx.fill();
  ctx.lineWidth = 1.1 * u;
  ctx.strokeStyle = 'rgba(255,255,255,0.18)';
  ctx.beginPath();
  ctx.arc(cx, cy, R * 1.12, 0, Math.PI * 2);
  ctx.stroke();
  if (p > 0) {
    ctx.strokeStyle = '#50ff8c';
    ctx.beginPath();
    ctx.arc(cx, cy, R * 1.12, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * Math.min(1, p));
    ctx.stroke();
  }
  // 沒在舉手時，圖示上下跳動吸引注意
  const bob = p > 0 ? 0 : Math.sin(now / 250) * 0.5 * u;
  drawStick(ctx, cx, cy + R * 0.8 + bob, R * 1.5, { armsUp: true, color: p > 0 ? '#50ff8c' : '#ffffff' });

  text(ctx, '雙手舉過頭頂開始', cx, cy + R * 1.3 + 5.5 * u, 5 * u, '#ffffff');
  const sub = !s.present ? '站到地上的腳印，面向螢幕' : p > 0 ? '撐住別放下…' : '看到你了！雙手舉過頭頂';
  text(ctx, sub, cx, cy + R * 1.3 + 10.5 * u, 3.2 * u, s.present ? '#4fd1ff' : '#9fb3d9');
}
