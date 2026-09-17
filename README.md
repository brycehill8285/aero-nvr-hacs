# Aero NVR for Home Assistant

Brings an [Aero NVR](https://github.com/brycehill8285/nvr-app) server into Home Assistant:
cameras, motion and object sensors, event pictures, and detection switches.

Aero keeps doing the recording and the AI work. This integration only reads state and
flips settings — video is played straight from Aero's own go2rtc, so nothing is
re-encoded and no second detection pipeline is started.

## Setup

1. In Aero, go to **Settings → Add-ons** and install the **Home Assistant** add-on.
2. Open it and press **Generate token**.
3. In Home Assistant, add this repository in HACS, install **Aero NVR**, then go to
   **Settings → Devices & Services → Add Integration → Aero NVR**.
4. Enter the address of your Aero server (for example `192.168.1.50:2525`) and the token.

Removing the add-on in Aero revokes every token and closes the API.

## What you get, per camera

| Entity | Notes |
| --- | --- |
| Camera (main) | Full-resolution stream |
| Camera (low resolution) | The sub stream, where one is configured — use this in grids |
| Motion | Binary sensor |
| Person / Car / Animal detected | Binary sensors, unavailable when that class is switched off in Aero |
| Person / Car / Animal count | How many are on camera now |
| Last event / Last event time | What Aero last recorded |
| Last event image | The saved crop, pinned to its event id |
| Last recognized person | Who Aero last put a name to -- independent of Last event, which can be a stranger or a car |
| Last plate read | The most recent licence plate read -- independent of Last event the same way |
| Last recognized person image / Last plate read image | The photo behind each of the above, pinned to its event id (disabled by default) |
| Problem | On when the camera's analysis worker has stalled (disabled by default) |
| Decoder | Which decoder the stream got (diagnostic, disabled by default) |
| Switches | Recording, detect people/vehicles/animals/faces/plates, event search indexing |

Toggling a detection switch does not interrupt recording.

## Media Browser

Recorded footage is browsable from Home Assistant's **Media** panel: Aero NVR -> a
camera -> a day -> a clip. Playback is proxied through Home Assistant itself (the
frontend has no session cookie for Aero and can't attach the integration's token to a
plain video fetch), so nothing extra needs opening up on your network for it to work.

## Notifications

A blueprint ships in this repo for phone alerts with a snapshot attached, built on
the entities above (no extra setup on Aero's side):

1. In Home Assistant, go to **Settings → Automations & Scenes → Blueprints → Import
   Blueprint**.
2. Paste this URL:
   `https://raw.githubusercontent.com/brycehill8285/aero-nvr-hacs/main/blueprints/automation/aero_nvr/notify_on_detection.yaml`
3. Create an automation from it, pick the "Person/Vehicle/Animal detected" sensors to
   watch (not the plain "Motion" sensor -- that fires far more often) and which phone
   to notify.

The notification's picture comes from that camera's "Last event image" entity, so it
always matches whatever triggered the alert rather than a live frame taken after the
fact.

## Requirements

- Aero NVR with the Home Assistant add-on installed
- Home Assistant 2024.12 or newer
- Home Assistant must be able to reach the Aero server on its web port and on
  RTSP port 8554 (go2rtc), which is how live video is played
