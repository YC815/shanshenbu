export const CONFIG = {
  /** 待機時雙手舉過頭頂這麼久就開局 */
  START_HOLD_S: 1.5,
  /** 舉手時手短暫掉下來（或漏偵測）不中斷計時的寬限 */
  HANDS_GRACE_S: 0.3,
  COUNTDOWN_S: 3,
  HP: 3,
  WARN_S: 0.7,
  FLIGHT_S: 1.6,
  /**
   * 核彈出現後就開始算動作（玩家看到預警就會直接動，要接住）；
   * 但最早在出現後這麼久才結算「閃過」，讓玩家先看到核彈飛出來
   */
  RESOLVE_AFTER_S: 0.95,
  SHAKE_NEED_S: 0.5,
  /** 側方核彈：核彈出現後左右或前後移動這麼遠也算閃過 */
  DODGE_SHIFT_M: 0.25,
  GAP_START_S: 2.0,
  GAP_END_S: 0.7,
  FIRST_GAP_S: 1.0,
  /** 閃過這麼多顆就贏 */
  WIN_DODGES: 10,
  ABSENT_ABORT_S: 2,
  RESULT_S: 5,
};
