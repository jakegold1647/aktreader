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

## Project-bound recognition

For an imported AKT Reader document, run the same pinned configuration directly against the
project instead of preparing a PAGE XML file and image directory yourself:

    aktreader project-kraken-recognize E:\projects\serock.aktproj --manifest-sha256 <project-import-manifest-sha256> --config E:\AKTREADER_LOCAL\kraken.config.json

The command materializes a temporary PAGE XML input from the project's effective human text,
line/region geometry, and reading order, then copies its checksum-verified image objects beside
that input under safe generated names. It invokes the same local, pinned Kraken process and imports
the PAGE XML result as an aligned `kraken` suggestion before removing the temporary workspace.

The original source PAGE XML and image paths do not need to remain available after import, and the
command does not expose a workspace path, upload a scan, download a model, or replace a human
revision. The resulting suggestion appears in the local workbench for explicit human review.

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

## Training-data readiness

Do not turn a reviewed project into HTR training data merely because it has correct text. Before
any PAGE XML training export, each line must have a current human revision and a matching active
training-consent grant from the same editor. A grant binds the exact revision text; saving a later
revision makes the earlier grant ineligible. The granting contributor can append a withdrawal,
which prevents later exports from using that grant.

    aktreader project-grant-training-consent E:\projects\serock.aktproj --manifest-sha256 <project-import-manifest-sha256> --contributor local-user --all-human-revised
    aktreader project-training-readiness E:\projects\serock.aktproj --manifest-sha256 <project-import-manifest-sha256> --output E:\reports\serock-training-readiness.json

The readiness report names only opaque source-span IDs and records no source text. It is ready
only when every imported line is both human-revised and actively consented. This gate currently
does not export, publish, or train data; the following corpus-export step will consume its
content-addressed readiness evidence.

## Consented PAGE XML training bundle

After `project-training-readiness` reports `READY_FOR_PAGEXML_TRAINING_EXPORT`, create a
split-pinned local bundle:

    aktreader project-export-consented-training-pagexml E:\projects\serock.aktproj --manifest-sha256 <project-import-manifest-sha256> --split train --output-directory E:\training\serock-train

The bundle contains rewritten PAGE XML, copies of only the project’s checksum-verified source
images, a `train.lst`/`validation.lst`/`test.lst` file, and `bundle.aktreader.json`. It does not
contain original source paths, a server address, credentials, or a model. A PAGE XML import may
receive one immutable split only, preventing later train/validation/test leakage through that
project import.

Use a separately provisioned Kraken installation to compile or train locally. The current
[Kraken recognition-training guide](https://kraken.re/main/user_guide/training_recognition.html)
documents `ketos compile -f xml -o training.arrow document.page.xml` for PAGE XML data and
`ketos train` with explicit training and validation manifests. The bundle intentionally does not
launch either command: model pins, train/validation bundle selection, and the final experiment
recipe are separate auditable decisions.

## Multi-project corpus assembly

A bundle is the consented output of one project import. Build a trainer-ready corpus from a local
plan when there are at least two independently assigned imports: one or more `train` inputs and
one or more `validation` inputs. The plan uses the
`aktreader-local-htr-corpus-plan` 1.0.0 contract and contains only `project`,
`manifest_sha256`, and `split` for each input.

    aktreader htr-build-corpus --plan E:\training\corpus-plan.json --output-directory E:\training\serock-htr-corpus

Before copying any PAGE XML, the command rereads each source project's current revision and consent
state. A later revision without new consent, a revoked grant, duplicate source PAGE XML, a missing
validation split, or a split mismatch stops the build. The completed corpus contains isolated
per-import bundles under `data/`, ordered `train.lst` and `validation.lst` manifests, and
`corpus.aktreader.json`; the receipt intentionally excludes the source-project paths from the plan.

From the corpus directory, the recorded train command is:

    ketos train -f xml -t train.lst -e validation.lst

It deliberately supplies both manifests and never asks Kraken to choose its random `--partition`
split. If the plan also contains a `test` input, run the recorded evaluation form after training:

    ketos test -f xml -e test.lst -m <local-model-weights>

Inspect a corpus immediately before training:

    aktreader htr-inspect-corpus --plan E:\training\corpus-plan.json --corpus-directory E:\training\serock-htr-corpus

Inspection repeats the current-consent check and validates the plan hash, each bundle receipt, PAGE
XML, image checksum, and root split manifest. It does not invoke a model. A changed or withdrawn
revision therefore makes the corpus ineligible until it is rebuilt.

Corpus assembly and inspection check only local files. They do not install Kraken, invoke `ketos`,
or allow a network setting.

## Pinned local training

To run a fresh local training job, copy
[local-kraken-training.config.example.json](../examples/local-kraken-training.config.example.json)
to an untracked path and replace its executable path and placeholder checksum. The configuration
requires the exact SHA-256 of a local non-UNC `ketos` executable and explicit deterministic
runtime, architecture, normalization, split, and optimization settings. It accepts no remote
endpoint, credential, model-download, or arbitrary command field.

    aktreader kraken-train --config E:\AKTREADER_LOCAL\kraken-training.json --plan E:\training\corpus-plan.json --corpus-directory E:\training\serock-htr-corpus --output-directory E:\training\serock-training-run

The runner repeats corpus inspection immediately before launching `ketos --config … train` with
no shell, an allow-listed credential-free environment, and offline Hugging Face/Transformers
settings. It writes the generated experiment, stdout, stderr, safetensors weights, and a
checksum receipt to a temporary sibling directory; only a successful run with at least one
weights file is published atomically. The receipt pins the executable, corpus, plan, options,
logs, and produced artifacts without exposing local source paths.

This runner trains a fresh local model only. It does not install Kraken, resume or fine-tune a
previous model, upload artifacts, or make a hosted-service claim.

## Held-out local evaluation

Evaluation is available only when the same corpus plan includes a non-empty `test` split. Copy
[local-kraken-evaluation.config.example.json](../examples/local-kraken-evaluation.config.example.json)
to an untracked path and replace the local executable and model pins. The selected
`.safetensors` model must be a checksummed output named in the supplied training-run receipt,
and its receipt must match the corpus and plan that are still current and consent-eligible.

    aktreader kraken-evaluate --config E:\AKTREADER_LOCAL\kraken-evaluation.json --plan E:\training\corpus-plan.json --corpus-directory E:\training\serock-htr-corpus --training-run-directory E:\training\serock-training-run --output-directory E:\training\serock-evaluation-run

The runner invokes the documented `ketos test` form with explicit XML format, batch size,
normalization, and whitespace policy. It uses the same credential-free offline environment as
training and atomically publishes stdout, stderr, and
`evaluation-run.aktreader.json`. The receipt pins the current corpus, plan, executable, exact
training-run receipt, model, test manifest, and option set. Kraken's human-readable CER/WER and
confusion report is retained verbatim in the logs; AKT Reader does not invent a separate metrics
schema for it.


## Local service recognition queue

A service owner can make the already-pinned local Kraken runner available to
authorized editors as a durable loopback job. The browser never receives an
executable path, model path, configuration file, command arguments, or output
streams. It can queue recognition only for a document that is already in an
authorized local project.

Start the local service with an untracked checksum-pinned inference
configuration:

    aktreader service-serve E:\AKTREADER_SERVICE --kraken-config E:\AKTREADER_LOCAL\kraken.json

The service validates the configuration and artifact checksums before opening
its loopback listener. Its startup JSON and `GET /api/healthz` report
`kraken_recognition_enabled`; without the flag, the usual review and backup
features continue to work but recognition requests are rejected.

An `EDITOR` or `OWNER` can submit only the project document's
`manifest_sha256` to `POST /api/projects/<project-id>/recognitions/kraken`.
The worker materializes the project's effective PAGE XML and managed image
copies, invokes the configured local runner, then imports the result as
reviewable HTR suggestions. It retains a durable job receipt containing the
manifest, PAGE XML result checksum, suggestion count, and runtime fingerprint,
but never local file paths or process output.

Keep the same `--kraken-config` available when restarting a service that has
pending recognition jobs. A restarted service without that configured runner
will safely mark such a job failed rather than accepting a browser-supplied
replacement.
