from perf import Perf


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_關閉時不記錄也不印(capsys):
    p = Perf(log_s=0)
    p.add("camera", "wait", 5)
    p.tick("camera")
    assert capsys.readouterr().out == ""


def test_每_log_s_印一行中位數與_Hz(capsys):
    clock = Clock()
    p = Perf(log_s=5, clock=clock)
    for i in range(10):
        p.add("camera", "wait", 2.0)
        p.add("camera", "align", 8.0 if i % 2 else 9.0)
        p.add("pose", "detect", 7.0)
        p.tick("camera")
        p.tick("pose")
    assert capsys.readouterr().out == ""  # 還沒到 5 秒
    clock.t = 5.0
    p.tick("camera")
    out = capsys.readouterr().out.strip()
    assert out == "perf 5s | camera 2.2Hz wait 2.0 align 8.5 | pose 2.0Hz detect 7.0"


def test_印完歸零():
    clock = Clock()
    p = Perf(log_s=1, clock=clock)
    p.add("video", "jpeg", 3)
    clock.t = 1.0
    p.tick("video")
    assert not p._ms and not p._ticks
