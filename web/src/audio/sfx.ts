import { CONFIG as C } from '../game/config';
import type { GameSound } from '../game/game';

export type Clip = 'step' | 'bear';
// 動作提示音檔不進 git（見 audio/README.md）；沒放檔案時 glob 是空的，就只有合成音效
const FOUND = import.meta.glob<string>('../../../audio/*.mp3', { eager: true, query: '?url', import: 'default' });
const CLIP_FILES: Record<Clip, string> = { step: '閃身.mp3', bear: '狗熊.mp3' };
const CLIP_URLS = Object.fromEntries(
  (Object.entries(CLIP_FILES) as [Clip, string][]).flatMap(([clip, file]) => {
    const url = FOUND[`../../../audio/${file}`];
    return url ? [[clip, url]] : [];
  }),
) as Partial<Record<Clip, string>>;

/** Web Audio 即時合成音效，不需要音檔。瀏覽器規定要先有使用者操作才能出聲，見 unlock()。 */
export class Sfx {
  private ctx: AudioContext | null = null;
  private master!: GainNode;
  private noiseBuf!: AudioBuffer;
  /** 飛行中的核彈聲，閃過／被炸時要切掉 */
  private flying: { stop: (t: number) => void } | null = null;
  private clips: Partial<Record<Clip, AudioBuffer>> = {};
  private clipSrc: AudioBufferSourceNode | null = null;

  unlock() {
    if (!this.ctx) {
      const ctx = new AudioContext();
      this.ctx = ctx;
      this.master = ctx.createGain();
      this.master.gain.value = 0.7;
      this.master.connect(ctx.destination);
      this.noiseBuf = ctx.createBuffer(1, ctx.sampleRate * 2, ctx.sampleRate);
      const d = this.noiseBuf.getChannelData(0);
      for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
      for (const [name, url] of Object.entries(CLIP_URLS) as [Clip, string][]) {
        fetch(url)
          .then((r) => r.arrayBuffer())
          .then((b) => ctx.decodeAudioData(b))
          .then((buf) => (this.clips[name] = buf))
          .catch((e) => console.warn(`音檔載入失敗 ${url}`, e));
      }
    }
    void this.ctx.resume();
  }

  get ready() {
    return this.ctx?.state === 'running';
  }

  play(e: GameSound) {
    if (!this.ready) return;
    const t = this.ctx!.currentTime;
    switch (e) {
      case 'tick':
        return this.tone(660, t, 0.12, 'square', 0.2);
      case 'go':
        return this.tone(1320, t, 0.4, 'square', 0.22);
      // 核彈生成：播對應的動作提示音檔，每顆一次
      case 'warn_side':
        return this.clip('step');
      case 'warn_top':
        return this.clip('bear');
      case 'launch_side':
        return this.startFlying(this.rocket(t));
      case 'launch_top':
        return this.startFlying(this.fallingWhistle(t));
      case 'dodge':
        this.stopFlying(t);
        this.whoosh(t, 0.25);
        this.tone(880, t, 0.09, 'triangle', 0.25);
        this.tone(1320, t + 0.08, 0.18, 'triangle', 0.25);
        return;
      case 'hit':
        this.stopFlying(t);
        return this.explosion(t);
      case 'win':
        this.stopFlying(t);
        [523, 659, 784, 1047].forEach((f, i) => this.tone(f, t + 0.25 + i * 0.14, i === 3 ? 0.6 : 0.16, 'triangle', 0.3));
        return;
      case 'lose':
        this.stopFlying(t);
        this.tone(400, t + 0.6, 1.2, 'sawtooth', 0.2, 70);
        return;
    }
  }

  /** 播放動作提示音檔；同時只播一個，新的會切掉舊的 */
  private clip(name: Clip) {
    const buf = this.clips[name];
    if (!buf) return;
    this.clipSrc?.stop();
    const src = this.ctx!.createBufferSource();
    src.buffer = buf;
    src.connect(this.master);
    src.start();
    this.clipSrc = src;
  }

  stopAll() {
    if (this.ctx) this.stopFlying(this.ctx.currentTime);
    this.clipSrc?.stop();
    this.clipSrc = null;
  }

  // ---------------------------------------------------------------------

  private tone(freq: number, at: number, dur: number, type: OscillatorType, vol: number, freqEnd?: number) {
    const ctx = this.ctx!;
    const osc = ctx.createOscillator();
    const g = ctx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, at);
    if (freqEnd) osc.frequency.exponentialRampToValueAtTime(freqEnd, at + dur);
    g.gain.setValueAtTime(0, at);
    g.gain.linearRampToValueAtTime(vol, at + 0.01);
    g.gain.exponentialRampToValueAtTime(0.001, at + dur);
    osc.connect(g).connect(this.master);
    osc.start(at);
    osc.stop(at + dur + 0.05);
  }

  private noise(at: number, dur: number) {
    const src = this.ctx!.createBufferSource();
    src.buffer = this.noiseBuf;
    src.loop = true;
    src.start(at);
    src.stop(at + dur + 0.05);
    return src;
  }

  private startFlying(f: { stop: (t: number) => void }) {
    this.flying?.stop(this.ctx!.currentTime);
    this.flying = f;
  }

  private stopFlying(t: number) {
    this.flying?.stop(t);
    this.flying = null;
  }

  /** 側方：火箭推進——帶通噪音由低掃到高（越來越近）+ 低頻轟鳴 */
  private rocket(at: number) {
    const ctx = this.ctx!;
    const dur = C.FLIGHT_S;
    const src = this.noise(at, dur);
    const bp = ctx.createBiquadFilter();
    bp.type = 'bandpass';
    bp.Q.value = 1.2;
    bp.frequency.setValueAtTime(300, at);
    bp.frequency.exponentialRampToValueAtTime(2500, at + dur);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.05, at);
    g.gain.linearRampToValueAtTime(0.5, at + dur);
    src.connect(bp).connect(g).connect(this.master);

    const rumble = ctx.createOscillator();
    rumble.type = 'sawtooth';
    rumble.frequency.setValueAtTime(55, at);
    rumble.frequency.linearRampToValueAtTime(90, at + dur);
    const lp = ctx.createBiquadFilter();
    lp.type = 'lowpass';
    lp.frequency.value = 200;
    const rg = ctx.createGain();
    rg.gain.setValueAtTime(0.05, at);
    rg.gain.linearRampToValueAtTime(0.25, at + dur);
    rumble.connect(lp).connect(rg).connect(this.master);
    rumble.start(at);
    rumble.stop(at + dur + 0.05);
    return { stop: (t: number) => fadeOut([g, rg], t) };
  }

  /** 上方：炸彈下墜的哨音，音高一路往下掉 */
  private fallingWhistle(at: number) {
    const ctx = this.ctx!;
    const dur = C.FLIGHT_S;
    const osc = ctx.createOscillator();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(2200, at);
    osc.frequency.exponentialRampToValueAtTime(450, at + dur);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.04, at);
    g.gain.linearRampToValueAtTime(0.22, at + dur);
    osc.connect(g).connect(this.master);
    osc.start(at);
    osc.stop(at + dur + 0.05);
    return { stop: (t: number) => fadeOut([g], t) };
  }

  private whoosh(at: number, dur: number) {
    const ctx = this.ctx!;
    const src = this.noise(at, dur);
    const hp = ctx.createBiquadFilter();
    hp.type = 'bandpass';
    hp.frequency.setValueAtTime(3000, at);
    hp.frequency.exponentialRampToValueAtTime(600, at + dur);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.4, at);
    g.gain.exponentialRampToValueAtTime(0.001, at + dur);
    src.connect(hp).connect(g).connect(this.master);
  }

  /** 爆炸：低通掃頻的噪音 + 低頻重擊 */
  private explosion(at: number) {
    const ctx = this.ctx!;
    const dur = 1.6;
    const src = this.noise(at, dur);
    const lp = ctx.createBiquadFilter();
    lp.type = 'lowpass';
    lp.frequency.setValueAtTime(4000, at);
    lp.frequency.exponentialRampToValueAtTime(150, at + dur);
    const g = ctx.createGain();
    g.gain.setValueAtTime(1.0, at);
    g.gain.exponentialRampToValueAtTime(0.001, at + dur);
    src.connect(lp).connect(g).connect(this.master);
    this.tone(110, at, 0.7, 'sine', 0.9, 30);
  }
}

function fadeOut(gains: GainNode[], t: number) {
  for (const g of gains) {
    g.gain.cancelScheduledValues(t);
    g.gain.setValueAtTime(g.gain.value, t);
    g.gain.linearRampToValueAtTime(0, t + 0.08);
  }
}
