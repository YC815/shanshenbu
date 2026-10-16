export const CONFIG = {
  /** 待機時雙手舉過頭頂這麼久就開局 */
  START_HOLD_S: 1.5,
  /** 舉手時手短暫掉下來（或漏偵測）不中斷計時的寬限 */
  HANDS_GRACE_S: 0.3,
  COUNTDOWN_S: 3,
  HP: 3,
  WARN_S: 0.7,
  FLIGHT_S: 1.6,
  /** 上方追蹤導彈：一出現就開始算揮手，最早在出現後這麼久才結算「閃過」，讓玩家先看到它飛出來 */
  RESOLVE_AFTER_S: 0.95,
  SHAKE_NEED_S: 0.5,
  /** 側方核彈瞄準出現當下的位置；飛到時離那個位置（左右、上下、前後任一）這麼遠才算躲過 */
  DODGE_SHIFT_M: 0.3,
  GAP_START_S: 2.0,
  GAP_END_S: 0.7,
  FIRST_GAP_S: 1.0,
  /** 閃過這麼多顆就贏 */
  WIN_DODGES: 10,
  ABSENT_ABORT_S: 2,
  RESULT_S: 5,
};
