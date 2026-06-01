# Dashboards

Importable /IOTCONNECT dashboard for this demo.

## `nuc-vlm-dashboard.json`

A complete dashboard for the construction-VLM device:

- **Status tiles** (image transformations) — `excavator_present`, `person_in_danger_zone`,
  `person_present`, `hazard_detected`, `ppe_compliant` (green/alert icons).
- **On Device View** — embeds the device's live viewer (`http://<device-ip>:8080`).
- **RESOURCES gauges** — SoC temp, CPU %, memory % and MB.
- **PERFORMANCE gauges** — VLM latency, FPS.
- **WORKLOADS gauges** — NPU %, NPU freq, NPU memory, GPU freq, GPU %.
- **SET VLM** switch + **Std Prompt** control — `set-vlm` / `capture` commands.
- **Live LineChart** — per-class counts over time.
- **Device Command** panel — send any command (`ask-vlm`, `set-vlm`, …).
- **Location** map — plots the device from the `location` (LATLONG) attribute.

Gauge ranges/colors follow [`../IOTCONNECT-TEMPLATE.md`](../IOTCONNECT-TEMPLATE.md).

## Importing

1. In the /IOTCONNECT web UI: **Dashboards → Create Dashboard → Import**, select
   `nuc-vlm-dashboard.json`.
2. **Bind the widgets to your device** (the export references a device named
   `NUC15vlm` — choose your own). Widgets map to telemetry by **attribute name**,
   so your device must use the template in [`../iotc-template/`](../iotc-template/).
3. Update the **On Device View** widget URL to `http://<your-device-ip>:8080/`.

## Notes
- The status-tile icons load from Avnet-hosted S3 URLs baked into the export — no
  local assets needed.
- The status tiles compare to lowercase `true`/`false` (the device sends booleans
  as lowercase strings), which is why those template attributes are **STRING**.
