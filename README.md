# Get By

Get By finds small paid tasks that can cover a bill shortfall. Scan a bill, choose a brief, submit the work and follow the reward through buyer review and collection. The ring changes when the ledger receives a confirmed payment.

[Run the app](#run-the-app) · [Try the $30 challenge](#try-the-30-challenge) · [Connect PayPal Sandbox](#connect-paypal-sandbox) · [Understand the scouts](#how-the-scouts-work) · [Verify the build](#verify-the-build)

<br />

## Run the app

Use Python 3.9+, Tesseract on your PATH, and Ollama. Each judge runs a separate local instance. A laptop microphone is optional. The app includes two sample bills, a synthetic Korean recording and an original still-life sample.

```sh
git clone https://github.com/hkalbertkim/getby.git
cd getby
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

On macOS, `brew install tesseract ollama` installs the two command-line tools. On Linux install Tesseract with your package manager and use the [Ollama installer](https://ollama.com/download). Start Ollama in one terminal if it is not already running.

```sh
ollama serve
```

In a second terminal run the following commands. The first model download needs internet access.

```sh
ollama pull gemma3:4b
scripts/run.sh practice
```

Open **http://localhost:8765**. If that port is occupied, run `PORT=18945 scripts/run.sh practice`. The practice ledger works without payment credentials. Each scout identifies the model it used. If model inference fails it shows the eligibility fallback explicitly.

<br />

## Try the $30 challenge

| Action | What to look for |
|---|---|
| In **Bills**, scan the electricity sample and save it. Repeat for mobile. You can also upload a JPG or PNG. | Two sample statements total $80. The opening demo allocation is $50. The ring shows **$30 still to earn**. |
| In **Work**, choose Korean, 10 minutes and photo opportunities. Select **Find paid work**. | Three scouts read briefs in parallel. Open a result to see its scope, reward, estimated payday and match explanation. |
| Open **Record Korean phrases**. Record or select the sample, preview it, allow local review and submit. | The test buyer can play the recording. The ring still shows $30. |
| Open **Test buyer desk** in the footer. Approve the work and release the $12 reward. | Confirmed receipt brings the shortfall to $18. Refreshing preserves one receipt. |
| Submit the answer comparison with a reason. Check the receipt total of $13.20. Approve and release both rewards. | The $10 and $8 receipts close the shortfall. A wrong receipt total can be returned for editing. |
| List a new still life. In the buyer desk purchase **October photo royalty** and release its $4 reward. | The new listing remains unsold. Only the older sale counts toward the $84 available. |
| Pay the $50 electricity and $30 mobile bills. Open **Activity**. | Separate receipts and $4 remaining. Explore illustrative 30-day USDC options for the surplus. |

In practice mode all money movements take place in SQLite. Sandbox mode uses separate data and contacts PayPal. The $50 opening allocation is seeded in both modes. It represents a budget for the scenario and does not read a PayPal account balance. The buyer desk exposes both demo roles to a single operator on loopback. Keep personal bills and recordings on your own instance.

<br />

## Connect PayPal Sandbox

Use funded **Sandbox** accounts. The test buyer sends task rewards using Payouts. A worker receives these in a separate test account. Each test biller uses its own merchant REST app for an Orders checkout. Approve the test bill payment in PayPal as the worker and choose the funding source there. Get By does not verify which wallet funding source the payer selected.

Set these variables in the server environment or put them in `~/.config/getby/paypal.env` with restricted local access. Never put credentials in this repository.

| Variables | Account role |
|---|---|
| `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET` | Test buyer business app with Payouts enabled |
| `PAYPAL_RECIPIENT_EMAIL` | Worker’s Sandbox recipient email |
| `PAYPAL_ELECTRICITY_CLIENT_ID`, `PAYPAL_ELECTRICITY_CLIENT_SECRET` | Test electricity merchant |
| `PAYPAL_MOBILE_CLIENT_ID`, `PAYPAL_MOBILE_CLIENT_SECRET` | Test mobile merchant |

```sh
scripts/run.sh sandbox
```

When a Payouts item is pending, select **Check payout** in the buyer desk. The server checks the batch and item references, recipient, USD amount and item status before crediting the ledger. A timeout reuses the stored payment intent. A missing credential or rejected payout leaves the amount uncredited. A bill order reserves its amount while the worker can continue approval. A completed capture creates a bill receipt. An explicitly voided, uncaptured order releases its reservation. Each receipt has a unique provider reference and work or bill source.

[PayPal Sandbox accounts](https://developer.paypal.com/tools/sandbox/accounts/) · [Payouts API](https://developer.paypal.com/docs/api/payments.payouts-batch/v1/) · [Orders API](https://developer.paypal.com/docs/api/orders/v2/)

<br />

## How the scouts work

Speech, Evaluation and Licensing each filter the supplied buyer catalog by language, available time and photo permission. Each calls the local model with matching briefs, time constraints and the next due date. The catalog supplies prices, conditions and expected payment dates. The app compares those dates against the next bill. A contingent photo license stays in the opportunities list across the cycle.

**Explore external work sources** includes an on-demand GitHub search for open documentation bounties and links to participant or contributor portals. Availability and compensation require independent confirmation by the source. The four executable briefs belong to the included test buyer. Provider enrollment, scheduled utility debits, live stock marketplaces and on-chain investments are outside this judging build.

<br />

## Verify the build

```sh
.venv/bin/python -m unittest discover -s tests -v
```

The tests exercise OCR, revision and resubmission, unpaid photo listings, concurrent payout retries, partial bill payment, mismatched recipient and order identity, and recovery after interrupted or voided transactions. The provider tests use fixtures. A PayPal-issued transaction reference requires running Sandbox mode with funded test accounts.

SQLite files and submitted media stay under `.runtime/<mode>/`. To rerun the scenario without changing an existing session, use a fresh directory.

```sh
GETBY_DATA="$(mktemp -d)" PORT=18946 scripts/run.sh practice
```

The build uses Python, SQLite, Tesseract OCR, Pillow, Ollama, browser MediaRecorder, PayPal Payouts v1 and Orders v2. It uses an English interface and original test fixtures. [MIT License](LICENSE).
