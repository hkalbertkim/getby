"""Perform one repeatable $12 test payout for the synthetic Korean voice brief."""

import argparse
import base64
import os
from pathlib import Path
import sys
from sandbox_config import load_sandbox_settings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--send-test-reward",
        action="store_true",
        help="Submit one $12 PayPal Sandbox reward. Reuse this directory to retry.",
    )
    args = parser.parse_args()
    os.environ["GETBY_MODE"] = "sandbox"
    os.environ.setdefault("GETBY_DATA", str(ROOT / ".runtime/verification"))
    load_sandbox_settings()
    import paypal

    if not paypal.ready():
        print(
            "Sandbox setup incomplete. Configure the buyer app and PAYPAL_RECIPIENT_EMAIL. No request was sent."
        )
        return 2
    if not args.send_test_reward:
        print(
            "Sandbox buyer and recipient settings found. Use --send-test-reward to verify an actual test payout."
        )
        return 0
    import server

    server.init()
    try:
        server.save_bill(
            {
                "role": "electricity",
                "issuer": "Test electricity",
                "cents": 8000,
                "due": "2026-11-20",
            }
        )
        state = server.state()
        if "voice" not in state["work"]:
            server.discover(
                {"agent": "Speech", "language": "ko", "minutes": 10, "photos": False}
            )
            audio = (ROOT / "web/samples/voice.wav").read_bytes()
            server.submit(
                {
                    "id": "voice",
                    "consent": True,
                    "data": base64.b64encode(audio).decode(),
                    "mime": "audio/wav",
                }
            )
        if server.state()["work"]["voice"]["state"] == "submitted":
            server.review({"id": "voice", "decision": "approve"})
        current = server.settle("voice")
        work = current["work"]["voice"]
        print("PayPal payout state:", work["state"])
        if work["state"] == "received":
            receipt = next(e for e in current["ledger"] if e["source"] == "work/voice")
            print("Confirmed USD 12.00. PayPal receipt:", receipt["ref"])
            return 0
        print(
            "The reward has not been credited. Re-run with the same data directory to check this intent."
        )
        return 3
    except (server.Problem, paypal.PayPalError) as err:
        print(str(err), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
