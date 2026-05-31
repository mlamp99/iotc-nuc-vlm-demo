# credentials/

Put this device's Avnet /IOTCONNECT files here — they are **git-ignored** and
must never be committed:

- `iotcDeviceConfig.json`  (from the device's Info / Connection panel)
- the device certificate `*.crt`
- the device private key `*.pem`

Filenames don't matter; the app auto-detects them (see `app/credentials.py`).
Each physical device needs its **own** IOTCONNECT device and certs — see
`IOTCONNECT-TEMPLATE.md` → "Provisioning a new device".

To run without any cloud, set `IOTC_ENABLED=0` in `.env` and leave this empty.
