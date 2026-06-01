# /IOTCONNECT device template

`Intel-NUC-VLM-template.json` is an **importable** device template for this demo —
it defines all telemetry attributes (with types) and the cloud commands, so you
don't have to add them by hand.

## Import it
In the /IOTCONNECT web UI: **Devices → Device → Templates → Import Template**, then
choose `Intel-NUC-VLM-template.json`. Create your device from this template
(Self-Signed Certificate auth).

The human-readable reference for every attribute (with gauge ranges for the
dashboard) is in [`../IOTCONNECT-TEMPLATE.md`](../IOTCONNECT-TEMPLATE.md), and the
same tables are in the main README, section 6.

## Note on booleans
The device sends boolean fields (`person_present`, `ppe_compliant`,
`person_in_danger_zone`, `excavator_present`, `hazard_detected`,
`cloud_connected`) as **lowercase strings** `"true"`/`"false"`, so they are typed
**STRING** here (not BOOLEAN). Dashboard transforms should compare to lowercase
`true`/`false`.
