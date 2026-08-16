# Local Kraken PageXML recognition

AKT Reader can invoke an owner-provisioned local Kraken executable to recognize a
pre-segmented PAGE XML document. This is an interoperability adapter, not a bundled
Kraken installation: the application downloads no executable, model, or data and never
starts a server.

## What this adapter preserves

The command accepts existing PAGE XML, so its page, region, line geometry, and reading order
remain the input contract. Kraken returns a fresh PAGE XML result; it is not allowed to
overwrite the imported source. AKT Reader validates the result is local, well-formed PcGts XML
without DTD or entity declarations before atomically publishing it.

The result is an engine proposal. It is not a human transcription, a consensus result,
or training consent. Import it into an AKT project only after reviewing it against the
scan in the local workbench.

## Owner provisioning

Install Kraken and acquire a recognition model outside AKT Reader. Kraken's current
inference guide documents kraken -f xml ... ocr -m MODEL for recognition against
pre-segmented XML and -x for PAGE XML output. Use an exact local executable and model,
calculate their hashes, then copy examples/local-kraken.config.example.json to an
untracked local path and replace both paths and placeholder hashes.

    Get-FileHash -Algorithm SHA256 E:\AKTREADER_LOCAL\runtime\kraken.exe
    Get-FileHash -Algorithm SHA256 E:\AKTREADER_LOCAL\models\cyrillic-register.safetensors
    aktreader kraken-inspect --config E:\AKTREADER_LOCAL\kraken.config.json

kraken-inspect checks only local file existence and checksums; it does not execute Kraken.
The configuration accepts only cpu, mps, or cuda:N devices and a documented precision option.
URLs, UNC paths, endpoint fields, and credential fields are rejected.

## Recognition

    aktreader kraken-recognize --config E:\AKTREADER_LOCAL\kraken.config.json --pagexml E:\register\page.xml --output E:\register\page.kraken.xml

The adapter executes one checksum-pinned subprocess with shell=False, a credential-free
allow-listed environment, Hugging Face and Transformers offline flags, and an explicit timeout.
It uses Kraken's existing PAGE XML input path rather than resegmenting the page, then writes
the process output to a temporary local directory. Only a valid PAGE XML result is moved into
the requested output location. Pass --replace-existing only to replace a previous result.

This first adapter intentionally does not claim that an arbitrary available model can read
nineteenth-century Congress-Poland handwriting. Model selection, evaluation, and future
training require rights-cleared, human-reviewed data and clerk-year-separated evaluation.


## Importing suggestions into a project

After recognition, retain the JSON printed by the command: it contains the runtime fingerprint
and the result PAGE XML hash. The original project import prints its manifest SHA-256. Use both
to attach the result to that exact project import:

    aktreader project-import-htr-suggestions E:\projects\serock.aktproj E:\register\page.kraken.xml --manifest-sha256 <project-import-manifest-sha256> --engine kraken --runtime-fingerprint <kraken-runtime-fingerprint>

The project checks that every result page points at the same image bytes and dimensions, and that
the page identifiers, line identifiers, region identifiers, and line geometry exactly match the
imported source. It copies the result PAGE XML into content-addressed local project storage and
records its engine and runtime fingerprint. Any mismatch is rejected rather than guessed.

In the workbench, the newest aligned engine suggestion appears below the human editor. Using it
only copies text into the editor. Saving still appends a human revision and leaves both the
source PAGE XML and the engine proposal unchanged.

## Evaluating a pinned result

A recognition result is useful for model selection only after a reviewer has saved explicit
corrections. Evaluate the result hash returned by `project-import-htr-suggestions` against those
human revisions:

    aktreader project-evaluate-htr E:\projects\serock.aktproj --manifest-sha256 <project-import-manifest-sha256> --result-pagexml-sha256 <imported-result-pagexml-sha256> --output E:\reports\serock-kraken.json

The report records the engine and runtime fingerprint, and reports exact-line-match rate,
character error rate (CER), word error rate (WER), and all denominators. Text is normalized to
Unicode NFC only; case and whitespace remain significant. It evaluates only a line that has both
an imported engine suggestion and a later human revision. With none, the command writes a
`NO_EVALUABLE_HUMAN_REVISIONS` report rather than using source PAGE XML text as ground truth.
The report must live outside the project and will not replace an existing file unless
`--replace-existing` is explicit.
