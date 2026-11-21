from pathlib import Path
import argparse

from eyeseeyou_edge.replay import replay


def main():
    parser = argparse.ArgumentParser(description="Review fatigue alerts in an observation log.")
    parser.add_argument("observations", type=Path)
    args = parser.parse_args()
    events = {
        "request_fatigue_alert": [],
        "clear_fatigue_alert": [],
    }
    try:
        with args.observations.open("rb") as observations:
            for frame in replay(observations):
                action = frame["action"]
                if action in events:
                    events[action].append(frame["t_ms"])
    except (OSError, ValueError) as error:
        parser.exit(2, f"{args.observations}: {error}\n")
    for action, timestamps in events.items():
        times = ", ".join(str(timestamp) for timestamp in timestamps) or "-"
        print(f"{action}: {len(timestamps)} (ms: {times})")


if __name__ == "__main__":
    main()
