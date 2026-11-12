# Get By

**Tagline** — Turn a bill shortfall into small paid tasks with AI work scouts.

## Inspiration

A due-date reminder can tell someone that their electricity bill is coming. It cannot earn the missing $30. We wanted to start with that amount and find work that could realistically cover it.

## What it does

A user photographs a bill. Get By extracts the amount and due date, calculates the shortfall and matches small tasks to their time, language and permissions. The user can record Korean phrases, compare two answers, check a receipt or prepare a photo for licensing. A buyer reviews the actual submission. The dashboard separates work awaiting approval, expected income and money received.

In our sample month, two bills total $80 and the starting allocation is $50. Three tasks earn $30. A sale from last month’s photo catalog adds $4. After both bills are paid, that $4 belongs to the user.

## How we built it

Tesseract reads the statement. Three specialist scouts independently query a local Ollama model about eligible briefs. We keep amounts and dates in structured records. A Python service stores evidence and reconciles each payment in SQLite. Mobile browsers can record audio or upload a photo. The test buyer can replay the work before approving it.

The PayPal Sandbox adapter sends a task reward with Payouts, checks the item identity and terminal status, and uses Orders for each test merchant checkout. Every retry carries the original intent. A separate practice mode supplies a reproducible full cycle with local receipts. The trial briefs come from the included buyer catalog. A live public source search discovers open GitHub documentation bounties.

## What we learned

Submitting work, earning buyer approval and receiving money are three different events. Only confirmed receipts should change how much someone can use for a bill. A photo may sell next month, so its listing can remain useful even though it cannot cover today’s shortfall.

## What comes next

Connect real task suppliers, learn actual settlement delays by provider and support recurring bill cycles. We would measure how many dollars users collect before a bill is due and how much work it takes them to earn each dollar.

**Built with** Python, JavaScript, HTML, CSS, SQLite, Ollama, Gemma, Tesseract, Pillow, PayPal Payouts, PayPal Orders.
