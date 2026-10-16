import type { SensorState } from '../types';
import { CONFIG as C } from './config';

export type Phase = 'IDLE' | 'COUNTDOWN' | 'PLAYING' | 'WIN' | 'LOSE';
export type NukeKind = 'left' | 'right' | 'top';
export type GameSound = 'tick' | 'go' | 'warn_side' | 'warn_top' | 'launch_side' | 'launch_top' | 'dodge' | 'hit' | 'win' | 'lose';

export interface Nuke {
  kind: NukeKind;
  /** 生成後經過秒數 */
  t: number;
  /** 累計哆嗦毛秒數 */
  shake: number;
  /** 側方核彈的瞄準點：出現當下玩家的位置（m） */
  aim: { x: number; y: number; d: number };
}

export interface Flash {
  text: string;
  good: boolean;
  /** 核彈在瞄準點爆炸（被炸，或側方核彈撲空） */
  blast: boolean;
  t: number;
}

const NUKE_LIFE = C.WARN_S + C.FLIGHT_S;
const KINDS: NukeKind[] = ['left', 'right', 'top'];

export const nukeLife = NUKE_LIFE;
/** 預警結束、核彈飛行中 */
export const launched = (n: Nuke) => n.t >= C.WARN_S;

export class Game {
  phase: Phase = 'IDLE';
  phaseTime = 0;
  hp = C.HP;
  nuke: Nuke | null = null;
  gap = 0;
  /** 待機時雙手舉高累計秒數 */
  startHold = 0;
  private handsDown = 0;
  absentTime = 0;
  dodged = 0;
  flash: Flash | null = null;
  /** 這幀該播的音效，由 drainSounds() 取走 */
  private sounds: GameSound[] = [];

  constructor(private rng: () => number = Math.random) {}

  drainSounds(): GameSound[] {
    const out = this.sounds;
    this.sounds = [];
    return out;
  }

  update(dt: number, s: SensorState) {
    if (this.flash) {
      this.flash.t += dt;
      if (this.flash.t > 0.9) this.flash = null;
    }
    // 感測器不在線就暫停
    if (s.status !== 'ok') return;
    this.phaseTime += dt;

    switch (this.phase) {
      case 'IDLE':
        return this.updateIdle(dt, s);
      case 'COUNTDOWN':
        if (this.phaseTime >= C.COUNTDOWN_S) return this.startPlaying();
        if (Math.floor(this.phaseTime) !== Math.floor(this.phaseTime - dt)) this.sounds.push('tick');
        return;
      case 'PLAYING':
        return this.updatePlaying(dt, s);
      case 'WIN':
      case 'LOSE':
        if (this.phaseTime >= C.RESULT_S) this.setPhase('IDLE');
        return;
    }
  }

  private setPhase(p: Phase) {
    this.phase = p;
    this.phaseTime = 0;
  }

  /** 雙手舉過頭頂撐住才開局：站著不動的人（剛玩完的、路過的）不會被拉進下一場 */
  private updateIdle(dt: number, s: SensorState) {
    const up = s.present && s.hands_up;
    this.handsDown = up ? 0 : this.handsDown + dt;
    if (up) this.startHold += dt;
    else if (this.handsDown > C.HANDS_GRACE_S) this.startHold = 0;
    if (this.startHold >= C.START_HOLD_S) {
      this.startHold = 0;
      this.setPhase('COUNTDOWN');
      this.sounds.push('tick');
    }
  }

  private startPlaying() {
    this.setPhase('PLAYING');
    this.sounds.push('go');
    this.hp = C.HP;
    this.nuke = null;
    this.gap = C.FIRST_GAP_S;
    this.absentTime = 0;
    this.dodged = 0;
  }

  private updatePlaying(dt: number, s: SensorState) {
    this.absentTime = s.present ? 0 : this.absentTime + dt;
    if (this.absentTime >= C.ABSENT_ABORT_S) {
      this.nuke = null;
      return this.setPhase('IDLE');
    }
    if (!s.present) return;

    if (this.nuke) return this.updateNuke(dt, s);
    this.gap -= dt;
    if (this.gap <= 0) this.spawn(s);
  }

  /** 0..1，閃過越多核彈越密 */
  get progress() {
    return Math.min(1, this.dodged / C.WIN_DODGES);
  }

  private spawn(s: SensorState) {
    const kind = KINDS[Math.floor(this.rng() * KINDS.length)] ?? 'top';
    this.nuke = { kind, t: 0, shake: 0, aim: { x: s.x_m, y: s.y_m, d: s.distance_m } };
    this.sounds.push(kind === 'top' ? 'warn_top' : 'warn_side');
  }

  private updateNuke(dt: number, s: SensorState) {
    const n = this.nuke!;
    n.t += dt;
    if (n.t >= C.WARN_S && n.t - dt < C.WARN_S) this.sounds.push(n.kind === 'top' ? 'launch_top' : 'launch_side');
    if (n.kind === 'top') {
      // 追蹤導彈一直跟著頭，跑不掉，只能一直揮手把它甩開
      if (s.shaking) n.shake += dt;
      if (n.shake >= C.SHAKE_NEED_S && n.t >= C.RESOLVE_AFTER_S) return this.resolve(true);
      if (n.t >= NUKE_LIFE) this.resolve(false);
      return;
    }
    // 側方核彈打向出現當下的位置：飛到時人真的離開那裡才算躲過，做了什麼動作不重要
    if (n.t >= NUKE_LIFE) this.resolve(this.awayFromAim(n, s), true);
  }

  private awayFromAim(n: Nuke, s: SensorState): boolean {
    const { x, y, d } = n.aim;
    return Math.max(Math.abs(s.x_m - x), Math.abs(s.y_m - y), Math.abs(s.distance_m - d)) >= C.DODGE_SHIFT_M;
  }

  private resolve(dodged: boolean, blastAtAim = false) {
    this.nuke = null;
    this.gap = C.GAP_START_S + (C.GAP_END_S - C.GAP_START_S) * this.progress;
    if (dodged) {
      this.dodged++;
      this.flash = { text: '閃過！', good: true, blast: blastAtAim, t: 0 };
      this.sounds.push('dodge');
      if (this.dodged >= C.WIN_DODGES) {
        this.setPhase('WIN');
        this.sounds.push('win');
      }
      return;
    }
    this.hp--;
    this.flash = { text: '被炸！', good: false, blast: true, t: 0 };
    this.sounds.push('hit');
    if (this.hp <= 0) {
      this.setPhase('LOSE');
      this.sounds.push('lose');
    }
  }
}
