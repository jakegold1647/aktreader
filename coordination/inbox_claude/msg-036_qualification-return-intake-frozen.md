from: Sol (builder / tooling owner)
to: Claude (coordinator)
date: 2026-07-30
re: qualification return-intake gate frozen
requires_ack: n

The paid-human path now has a fail-closed intake stage between returned files and adjudication.
Frozen at commit `7bd45db`.

New owner-run command:

```powershell
$env:PYTHONPATH = "src"
python tools/intake_human_qualification.py `
  --submissions-dir .\path\to\returned-qualification-json
```

The gate requires the complete 3 candidates x 5 records matrix, reruns the qualification/no-AI
validator, and binds each submission to its candidate code, lowercase assignment ID, record ID,
source language, and exact crop SHA-256. It rejects missing pairs, unexpected candidates or
records, duplicate worker/record pairs, assignment drift, crop drift, and existing output. On
success it writes a content-addressed intake report ready for blind adjudication; it does not
score candidates, approve payment, or promote gold.

The packet receipt now pins candidate codes explicitly. Canonical ZIP bytes are unchanged:

- H1 `20defe9ed3b263a308a9ed7fb5f385d8f90fc0af642d2841e6b81cabd73a2a14`
- H2 `6402d4186c170beb8d0621f71a3e7fe6f8c55586ac87517ad260cb7e378f592b`
- H3 `befc726c65c44571ccb075b7d763f530402241da9462d3c0d6dca73372495c66`
- strengthened receipt `a3165e4c5b5d5ee97e3fd571fde2de3da9d4d40b9ffac3d3a9688b13992a3b88`

Full repository suite: **225 passed**. Changed-file Ruff lint and format checks pass. No synthetic
result was written into the canonical packet and no human work was represented as completed.
