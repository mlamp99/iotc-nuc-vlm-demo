# Dashboards

Importable /IOTCONNECT dashboard templates for this demo.

## `nuc-vlm-dashboard.json` (work in progress)

A starting dashboard with:
- **Resources** gauges — SoC temp, CPU %, memory % / MB
- **Performance** gauges — VLM latency, FPS
- **Workloads** gauges — NPU %/freq/memory, GPU %/freq
- **On Device View** — embeds the device's live MJPEG viewer (`http://<device-ip>:8080/`)
- **SET VLM** switch and **Std Prompt** control — send the `set-vlm` / `capture` commands
- **Live LineChart** — per-class counts (object/person/hardhat/vest/cone)
- **PPE Compliant** status tile (green/red)

> This dashboard is a starting point and will continue to evolve. Gauge ranges
> and color bands follow the recommendations in
> [`../IOTCONNECT-TEMPLATE.md`](../IOTCONNECT-TEMPLATE.md).

## Importing

1. In the /IOTCONNECT web UI: **Dashboards → Create Dashboard → Import** (or the
   import icon on the Dashboards page).
2. Select `nuc-vlm-dashboard.json`.
3. When prompted, **bind the widgets to your device** (the export references a
   device named `NUC15vlm`; choose your own device instead). Widgets map to
   telemetry by **attribute name**, so your device template must define the
   attributes listed in [`../IOTCONNECT-TEMPLATE.md`](../IOTCONNECT-TEMPLATE.md).
4. Update the **On Device View** widget URL to your device's address
   (`http://<your-device-ip>:8080/`).

## Notes
- The dashboard only renders attributes your device is actually publishing —
  make sure the device template includes the performance/health attributes
  (`soc_temp_c`, `npu_busy_pct`, `vlm_latency_s`, etc.).
- The embedded viewer requires the dashboard browser to reach the device on
  port 8080 (same LAN, or via a tunnel).
