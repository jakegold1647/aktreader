# Synthetic public service demo

This small, public fixture exercises the AKT Reader document lifecycle without distributing a scan,
a real register entry, a person’s data, or a model weight. Both the image and its PAGE XML are
synthetic. The transcription is deliberately fictional; it is not evidence about a person or an
archive record.

Create a local project and import it:

```powershell
python -m aktreader project-create demo.aktproj --name "AKT Reader public demo"
python -m aktreader project-import-pagexml demo.aktproj examples/public-demo/synthetic-demo.page.xml --image-root examples/public-demo
python -m aktreader project-inspect demo.aktproj
```

Optionally copy the demo project into a loopback service and explore the browser editor, exports,
search, artifact attachments, and backup flow:

```powershell
python -m aktreader service-create service-data
python -m aktreader service-user-create service-data --username owner --password-file owner-password.txt
python -m aktreader service-add-project service-data demo.aktproj --owner owner
python -m aktreader service-serve service-data --port 8780
```

Visit `http://127.0.0.1:8780/` and delete the temporary password file after setup. The service
never opens a LAN listener by default.

This fixture is not a benchmark, training corpus, OCR claim, or legal genealogical source. Use
actual historical material only when its provenance, consent, and distribution rights have been
reviewed.
