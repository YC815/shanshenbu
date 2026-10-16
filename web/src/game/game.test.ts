import { describe, expect, it } from 'vitest';
import type { SensorState, StepEvent } from '../types';
import { CONFIG as C } from './config';
import { Game } from './game';

const DT = 1 / 60;

function st(over: Partial<SensorState> = {}): SensorState {
  return {
    status: 'ok',
    present: true,
    distance_m: 4,
    x_m: 0,
    events: [],
    shaking: false,
    hands_up: false,
    ...over,
  };
}

function run(g: Game, seconds: number, s: SensorState | ((g: Game) => SensorState)) {
  for (let t = 0; t < seconds; t += DT) g.update(DT, typeof s === 'function' ? s(g) : s);
}

const UP = st({ hands_up: true });

/** rng 固定回傳 → 核彈種類固定：0=left, 0.4=right, 0.9=top */
function playing(rngValue: number) {
  const g = new Game(() => rngValue);
  run(g, C.START_HOLD_S + 0.05, UP);
  expect(g.phase).toBe('COUNTDOWN');
  run(g, C.COUNTDOWN_S + 0.05, st());
  expect(g.phase).toBe('PLAYING');
  return g;
}

/** 跑到核彈可以結算閃過的時間點 */
function untilNukeInWindow(g: Game) {
  run(g, C.FIRST_GAP_S + 0.05, st());
  expect(g.nuke).not.toBeNull();
  run(g, C.RESOLVE_AFTER_S, st());
}

describe('Game', () => {
  it('雙手舉高撐滿就倒數，倒數完開始', () => {
    playing(0);
  });

  it('只是站著（沒舉手）不會開始', () => {
    const g = new Game();
    run(g, 10, st());
    expect(g.phase).toBe('IDLE');
    run(g, 2, st({ present: false, hands_up: true }));
    expect(g.phase).toBe('IDLE');
  });

  it('舉手中手短暫掉下來不中斷，放下太久要重來', () => {
    const g = new Game();
    run(g, C.START_HOLD_S - 0.3, UP);
    run(g, C.HANDS_GRACE_S - 0.1, st());
    run(g, 0.35, UP);
    expect(g.phase).toBe('COUNTDOWN');
    const g2 = new Game();
    run(g2, C.START_HOLD_S - 0.3, UP);
    run(g2, C.HANDS_GRACE_S + 0.1, st());
    run(g2, 0.35, UP);
    expect(g2.phase).toBe('IDLE');
  });

  it('玩完回待機，原地站著不會自動開下一場', () => {
    const g = playing(0.9);
    while (g.phase === 'PLAYING') g.update(DT, st());
    run(g, C.RESULT_S + 5, st());
    expect(g.phase).toBe('IDLE');
  });

  it('左方核彈：判定窗內往右閃身步 → 閃過', () => {
    const g = playing(0);
    untilNukeInWindow(g);
    g.update(DT, st({ events: ['step_right'] }));
    expect(g.nuke).toBeNull();
    expect(g.hp).toBe(C.HP);
    expect(g.dodged).toBe(1);
  });

  it('左方核彈：往左閃也算閃過', () => {
    const g = playing(0);
    untilNukeInWindow(g);
    g.update(DT, st({ events: ['step_left'] }));
    expect(g.hp).toBe(C.HP);
    expect(g.dodged).toBe(1);
  });

  it('側方核彈：沒觸發閃身步，但橫移夠遠也算', () => {
    const g = playing(0.4);
    untilNukeInWindow(g);
    g.update(DT, st({ x_m: 0 }));
    g.update(DT, st({ x_m: -(C.DODGE_SHIFT_M + 0.01) }));
    expect(g.hp).toBe(C.HP);
  });

  it('側方核彈：往前跨（閃身步事件或距離變化）也算', () => {
    const g = playing(0);
    untilNukeInWindow(g);
    g.update(DT, st({ events: ['step_forward'] }));
    expect(g.dodged).toBe(1);
    const g2 = playing(0.4);
    untilNukeInWindow(g2);
    g2.update(DT, st({ distance_m: 3 }));
    g2.update(DT, st({ distance_m: 3 - (C.DODGE_SHIFT_M + 0.01) }));
    expect(g2.dodged).toBe(1);
  });

  it('側方核彈：站著不動 → 被炸', () => {
    const g = playing(0);
    run(g, C.FIRST_GAP_S + 0.05, st());
    run(g, C.WARN_S + C.FLIGHT_S, st());
    expect(g.hp).toBe(C.HP - 1);
  });

  it('預警一出現就閃也算，但要等核彈飛出來才結算', () => {
    const g = playing(0.4);
    run(g, C.FIRST_GAP_S + 0.05, st());
    g.update(DT, st({ events: ['step_left'] as StepEvent[] }));
    expect(g.nuke).not.toBeNull();
    expect(g.dodged).toBe(0);
    run(g, C.RESOLVE_AFTER_S, st());
    expect(g.nuke).toBeNull();
    expect(g.dodged).toBe(1);
    expect(g.hp).toBe(C.HP);
  });

  it('上方核彈：哆嗦毛滿 0.5 秒 → 閃過', () => {
    const g = playing(0.9);
    untilNukeInWindow(g);
    run(g, C.SHAKE_NEED_S + 0.05, st({ shaking: true }));
    expect(g.hp).toBe(C.HP);
    expect(g.dodged).toBe(1);
  });

  it('3 滴血扣完 → LOSE，5 秒後回 IDLE', () => {
    const g2 = playing(0.9);
    while (g2.phase === 'PLAYING') g2.update(DT, st());
    expect(g2.phase).toBe('LOSE');
    expect(g2.hp).toBe(0);
    run(g2, C.RESULT_S + 0.05, st());
    expect(g2.phase).toBe('IDLE');
  });

  it(`閃過 ${C.WIN_DODGES} 顆 → WIN`, () => {
    const g = playing(0);
    for (let i = 0; i < C.WIN_DODGES; i++) {
      expect(g.phase).toBe('PLAYING');
      while (!g.nuke || g.nuke.t < C.RESOLVE_AFTER_S) g.update(DT, st());
      g.update(DT, st({ events: ['step_right'] }));
    }
    expect(g.dodged).toBe(C.WIN_DODGES);
    expect(g.phase).toBe('WIN');
  });

  it('玩家消失 2 秒 → 作廢回 IDLE', () => {
    const g = playing(0);
    run(g, C.ABSENT_ABORT_S + 0.05, st({ present: false }));
    expect(g.phase).toBe('IDLE');
  });

  it('音效事件：倒數、開始、預警、發射、閃過', () => {
    const g = playing(0);
    expect(g.drainSounds()).toEqual(['tick', 'tick', 'tick', 'go']);
    run(g, C.FIRST_GAP_S + C.WARN_S + 0.05, st());
    expect(g.drainSounds()).toEqual(['warn_side', 'launch_side']);
    run(g, C.RESOLVE_AFTER_S - C.WARN_S, st());
    g.update(DT, st({ events: ['step_left'] }));
    expect(g.drainSounds()).toEqual(['dodge']);
  });

  it('感測器斷線時暫停', () => {
    const g = playing(0);
    run(g, 10, st({ status: 'disconnected' }));
    expect(g.phase).toBe('PLAYING');
    expect(g.nuke).toBeNull();
  });
});
