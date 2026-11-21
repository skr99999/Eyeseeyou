"""Replay a labeled eye closure at different sampling rates using the public Python API."""

import json

from eyeseeyou_edge.replay import replay


def observations(hz, duration_ms):
    for t_ms in range(0, 15001, 1000 // hz):
        closed = 10000 <= t_ms < 10000 + duration_ms
        yield json.dumps({
            "t_ms": t_ms, "face_found": True, "eye_state": "CLOSED" if closed else "OPEN",
            "ear": 0.1 if closed else 0.3, "mar": 0.1,
        }).encode("utf-8")


if __name__ == "__main__":
    print("closure_ms  Hz  actions (time in ms / input / action)")
    for duration in (1400, 1490, 2000):
        for hz in (5, 10, 20, 25, 50):
            actions = [f"{r['t_ms']} / {r['eye_state']} / {r['action']}"
                       for r in replay(observations(hz, duration)) if r["action"]]
            print(f"{duration:10} {hz:3}  {'; '.join(actions) or '-'}")
