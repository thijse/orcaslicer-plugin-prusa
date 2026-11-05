# Upstream Gaps & Findings for OrcaSlicer Python Plugins

During development of the Prusa XL multi-tool plugin, the following architectural gaps and limitations were identified in OrcaSlicer 2.5.0-dev. Sections 6 onward were found while running the plugin inside Orca.

## 1. Preset Credential Refresh Restricted to Moonraker
In `src/slic3r/GUI/DeviceManager.cpp`:
```cpp
if (printer_agent_id == MOONRAKER_PRINTER_AGENT_ID && config.opt_string("printer_agent") == MOONRAKER_PRINTER_AGENT_ID) {
    password = config.opt_string("printhost_apikey");
}
```
Only Moonraker has its password refreshed from the preset's API key field when connecting. For third-party Python agents, `PrinterConnectionParams.username` is always empty, and credentials must be maintained within the plugin's own capability configuration.

## 2. Missing Python Fallbacks for IPrinterAgent
In `PrinterAgentPluginCapabilityTrampoline.hpp`, methods such as `check_cert`, `ping_bind`, `bind`, `unbind`, and `request_bind_ticket` have default implementations in C++ returning success, but the Python trampoline expects overrides; omitting them in Python causes the C++ side to receive `-1` (failure). A Python agent must explicitly override and return `0`.

## 3. Web Device Tab CORS Override (`SendAPIKey`)
In `src/slic3r/GUI/PrinterWebView.cpp`:
When an API key is configured on a printer, OrcaSlicer overrides `window.fetch` globally in the embedded webview, injecting `X-API-Key` into all requests. This causes CORS preflight (`OPTIONS`) failures on single-page webapps like Prusa Connect (`https://connect.prusa3d.com`) that do not list `X-API-Key` in `Access-Control-Allow-Headers`.

## 4. Multi-tool Device Tab Layout
OrcaSlicer's native Device tab is hardcoded for Bambu Lab dual-extruder or single-extruder layouts. Printers with 5 tools (such as Prusa XL) must either be grouped into virtual 4-slot AMS units or displayed via a custom Pages tab capability (`orca.pages.PagesPluginCapabilityBase`).

## 5. WebRTC Camera Support Unavailable in Python
In `PrinterAgentPluginCapability.cpp`, `CameraStreamMode` supports `HTTP`, `HTTPS`, `RTSP`, and `HTTP_SNAPSHOT`. WebRTC is available only to compiled C++ agents.

## 6. A preset stores the agent id but Orca resolves it as a capability name
Saving a printer preset with `printer_agent = <agent id>` warns "Plugin Not Identified" and drops the `plugins` manifest entry unless the capability's `get_name()` equals `AgentInfo.id` (`ConfigBase::unresolved_plugin_capabilities` → `resolve_capability_fn` looks capabilities up by name). The plugin returns the agent id from `get_name()`. Upstream fix: resolve `printer_agent` through `NetworkAgentFactory`'s plugin identifier.

## 7. Plugin storage, reload and junctions
- `orca.host.plugin.storage()` is keyed by the entry file name (`plugin_data/prusa_plugin/`), not by the folder or plugin name.
- Plugins → Refresh does not reload changed plugin code; Orca must restart.
- A plugin folder that is a junction prompts once per source file, because the audit canonicalises the path outside `data_dir()`.

## 8. Network permissions: exact URLs vs hosts
`request_permissions(network_http=[url])` grants exact URLs only, so a LAN client polling several endpoints prompts for each; `network=[url]` grants the whole host. Run-time prompts are native modal dialogs that stack (one per poll) and block the UI thread, including MCP automation. The LAN host is only known at run time, so the plugin reads its own settings during `register_capabilities()` to request it up front.

## 9. The preset's machine is only selected after the agent announces it
`GUI_App::select_machine` selects a device only when it is already in the agent's machine list. A fresh agent must send an SSDP-style message (`set_on_ssdp_msg_fn`) for the preset's `print_host` from `start_discovery()`.

## 10. Device configs exist only for Bambu models
`dev_type` must be the vendor profile's `model_id` (e.g. `prusa_xl_5t_01`) for AMS sync to accept the printer (`Plater::is_same_printer_for_connected_and_selected`). But `_parse_printer_type` and `DevPrinterConfigUtil` read `resources/printers/<model>.json`, which exist only for Bambu, so a Prusa model logs "Unsupported printer type" and `get_printer_display_name()` is empty. Consequences:
- `MachineObject::update_printer_preset_name` fails on every status push.
- The Device tab's tray edit dialog (`AMSMaterialsSetting::Popup`) lists no filaments, so a tray's material can't be changed there. The plugin's Prusa tab offers this instead (Connect `UpdatePrinterMaterial`).
Upstream fix: fall back to the vendor profile's model name when there is no device config.

## 11. `Preset.filament_id` is not exposed to Python
`config_value("filament_id")` is empty because the id lives in `Preset::filament_id`, not the config. The plugin reads the preset JSON (`Preset.file`) and follows `inherits` to find it, which AMS sync needs to pick the right preset.

## 12. Print jobs live outside the plugin's allowed roots
`PrintParams.filename` is a `.gcode.3mf` in `<temp>/orcaslicer_model/...`, which isn't under `data_dir()`, so every read prompts. Answering such a prompt from a worker thread (the send job) denies the current call and only saves the grant afterwards, so the first send always fails. Plugins must declare `fs_read=["<temp>/orcaslicer_model/*"]` up front. Writes to `%TEMP%` prompt too, so the plugin writes its extracted G-code to its own storage folder. Upstream fix: make the job file a per-call scoped root while the agent's print methods run, as the slicing pipeline does for its G-code folder.

## 13. PrusaLink upload quirks (Buddy firmware 8.0.1)
- Send the whole file in one `PUT /api/v1/files/usb/<name>` with `X-Api-Key`. With Digest auth, urllib sends the body twice, and the second attempt times out (HTTP 408).
- Write the body in large blocks (1 MB). 64 kB writes get HTTP 500.
- `Overwrite: ?1` returns 500 when the target is "busy": the printer keeps the last uploaded file selected, and it can't be deleted (409) until another file is chosen. The plugin uploads under the first free name.
- Uploads run at about 20 kB/s. A 700 kB file takes about 40 s.
- `Print-After-Upload: ?0` doesn't stop the printer from asking on its screen whether to print the new file, so an Orca "Send" can still start a print if someone confirms it there.
- `PUT /api/v1/job/<id>/pause|resume` answers 204 at once; the state changes a few seconds later.

## 14. What a running print reports
- PrusaLink `/api/v1/status` has the job's id, progress and times but no file name; `/api/v1/job` adds the file (8.3 `name` plus `display_name`). Neither reports layers.
- Connect's printer record has `job_info.total_height`, and its job list (`/app/printers/<uuid>/jobs`) has the file's slicing metadata (`layer_height`, per-slot filament use, estimated time). The plugin derives Orca's `layer_num`/`total_layer_num` from those and the LAN Z height.
- Orca shows the Device-tab thumbnail only from a cloud task or `thumbnail_url`; PrusaLink's `/thumb/l/usb/<file>` needs auth, so it can't be passed as a plain URL.
- With no tool picked, the XL reports nozzle 0 over LAN (see `merge`). During a print the active tool is reported.
- A stop takes two polls: first the state stays `PRINTING` while targets drop to 0 and the head lifts (Z 8 → 40 mm, above the 36 mm model), then the state becomes `STOPPED` with progress 0 and the job gone. Layer estimates ignore a Z above the model.

- A normal finish also takes two polls: state `PRINTING` at 99 % with targets 0 and the head lifted to ~133 mm, then `FINISHED` with progress 0 and the job gone. The printer's time-left estimate reaches 0 a few minutes before the end (here at 98 %).
- Connect's printer record now and then omits the tool list (3 of ~140 polls); the plugin keeps the previous tools.
- Z alone misleads: before the first layer the XL probes and parks high (Z 5–15 mm), and a pause or stop lifts the head to about 40 mm. The plugin starts counting at the first layer and only accepts small upward steps.

## 15. Camera
- The Buddy3D camera supports RTSP (`RtspStream`), but it is off by default: no port answers on the camera's IP. Orca's RTSP mode needs it enabled in the camera's settings.
- Connect's camera page offers a stream selector (Disable / RTSP / WebRTC) only while its live socket to the camera is connected. RTSP and WebRTC are exclusive: turning RTSP on turns WebRTC off, so Connect's own live view stops. The camera reports its RTSP address as `system.rtsp_server.url`.
- Connect's GraphQL `CamerasByPrinter` returns `snapshots.lastSnapshotUrl` on `camera-service-snapshots.prusa3d.com`, readable with the same bearer token (1080p JPEG, refreshed every 30 s while printing). The Prusa tab shows it, and the Device tab shows it through `HTTP_SNAPSHOT` (see 17). Connect's WebRTC live stream is not reachable from a plugin (see 17).
- Live view in Connect runs over `wss://camera-signaling.prusa3d.com/socket.io/` (Socket.IO, protobuf payloads): the browser sends `client_authentication` with the camera token and the user's JWT, then `trigger` (`get_status`, `get_features`); the camera answers with `status` / `features` and WebRTC offers on `webrtc`, with ICE servers from `CAMERA_WEBRTC_CONFIG_URL`. Observed on this setup: authentication is acknowledged but the camera never answers, so Connect shows no live view or stream selector, and no client can get video. A WebRTC→RTSP/MJPEG bridge (e.g. go2rtc) would only help once the camera answers there.
- In `HTTP_SNAPSHOT` mode Orca's camera panel waits for the play button; it doesn't start by itself when the Device tab opens.

- PrusaLink thumbnails (`/thumb/l/usb/<file>`) answer 401 to Digest auth but 200 to `X-Api-Key`, and the XL takes 5-12 s per thumbnail. The plugin caches them in its storage folder. `/thumb/s/` returns 404 for every file tried.
- PrusaLink v1 (firmware 8.0.1) has no endpoints for temperatures, fans, motion or the light, so the Prusa tab's Control box is read-only.

## 16. Device Storage tab needs Bambu's file protocol
The Storage tab (`MediaFilePanel`/`PrinterFileSystem`) lists and prints files over Bambu's tunnel protocol, which a plugin agent cannot provide, so `start_sdcard_print` is never reached. The Prusa tab lists the printer's files (PrusaLink `GET /api/v1/files/usb/`) and starts one with `POST /api/v1/files/usb/<name>`. Upstream fix: an agent hook for listing storage files.

## 17. The Device tab looks like a Bambu printer
Most Device-tab visuals are hard-coded or read from `resources/printers/<model>.json`, which exists only for Bambu models and must ship with the app:
- The camera's idle picture (`live_stream_default.png`, Bambu Lab logo) shows for every non-snapshot mode. The plugin avoids it with `HTTP_SNAPSHOT`: it serves the latest Connect snapshot from a localhost server (needs a `socket.bind` grant for 127.0.0.1) unless the configured RTSP port answers.
- The extruder drawing has single- and dual-nozzle (H2D) variants only; nothing for 5 toolheads.
- The AMS panel is always shown while connected; the XL's tools appear as AMS units (one of 4 slots plus one of 1) with an empty "Ext" spool.
- The Update tab shows the generic printer thumbnail and an AMS picture.
- No agent hook supplies a device page, printer image or AMS visibility. Upstream fixes: a neutral idle image for non-Bambu agents, agent hooks for printer thumbnail / tool-changer layout / hiding AMS, and a non-Bambu device-config folder so a vendor can ship `printers/<model>.json` with images.
- Orca has a WebRTC camera player (`WebRtcMediaController`), but its signalling channel comes only from the Orca Cloud agent (`ICloudServiceAgent::create_camera_signaling_channel`); a printer agent can't provide one, so Connect's WebRTC live view can't be played.

## 18. Printer controls go through Prusa Connect only

PrusaLink (8.0.1) has no temperature, fan or motion endpoints. Connect runs `supported-commands` such as SET_NOZZLE_TEMPERATURE, SET_HEATBED_TEMPERATURE, SET_SPEED, HOME, MOVE, MOVE_Z and the SET_TOOL_* nozzle settings via `POST /app/printers/<uuid>/commands/sync`; each command lists the printer states it runs in (MOVE/MOVE_Z: not while printing). There is no fan command, so fans stay read-only. The Device tab's jog pad, home and temperature fields send G-code (`gcode_line`), which the plugin translates to these commands; push_status reports all axes homed so Orca doesn't stop at its "recenter" dialog.

## 19. A plugin page can't set filament slot colours

Slot colours are the project's `filament_colour` (the coloured number box in the Prepare sidebar); the dropdown swatches are each preset's own `default_filament_colour`, which overwrites the slot colour when that preset is selected (an empty one keeps it). The only plugin route to the slot colours is `orca.host.tools.call("set_settings", {"scope": "project", ...})`, and Orca allows tool calls only from Script workers and their threads, not from a Pages capability's message handler or the threads it starts. The Filament page therefore syncs the slot presets (`orca.host.preset.filament.begin_update(slot, preset_name)`) and points to the Device tab's Sync for colours. A host API for slot colours, or tool calls from page worker threads, would close this gap.

## 20. Print handover and tracking

- The agent's `start_print`/`start_send_gcode_to_sdcard` run on a worker thread (not the UI thread), so the plugin can show a blocking `orca.host.ui.message` there. The pre-flight check reads the plate G-code's config block (`filament_type`, `nozzle_diameter`, `filament_settings_id`) and the `T<n>` lines it selects, and compares them with the tools. Cancelling returns -1; Orca then shows "Failed to send the print job" with our text behind "Check the reason". A "cancelled by the user" result code would read better.
- The plugin API can't open a project in Orca (`Plater` has no `load_project` binding), so the History page's "Show project" opens the folder.
- Orca's tab bar collapses tabs into overflow arrows when the window is narrow; a plugin tab is then not reachable by name in the UI snapshot.
- History lives in `plugin_data/prusa_plugin/history.json` with snapshots in `history/`. A job is matched to the handover by file name; prints started on the printer or in Connect get their own record. Prints that end while Orca is closed end up as "unknown".

## 21. Other Buddy printers

- Printer identity comes from Connect's `printer_type` triple, matching Prusa-Firmware-Buddy `include/common/printer_model_data.hpp` (e.g. MK4S 1.4.1, MINI 2.1.0, XL 3.1.0, CORE One 7.1.0, INDX 7.10.0). `prusa_orca/printers.py` maps it to Orca's Prusa `model_id`; the XL and INDX pick the profile by tool count, MMU3 printers the MMU profile.
- Connect tool ids (Buddy `src/connect/tools.hpp`): heads are `"<n>"`, MMU3 feeder slots `"<head>.<slot>"`. With the MMU enabled the plugin shows the slots as trays/cards and keeps nozzle and temperatures from head `"0"`; material assignment uses the slot id.
- Extra controls (flow, chamber, enclosure) appear only when the printer's `supported-commands` lists them with a single argument; enclosure controls also need `enclosure.present`.
- Untested on real hardware other than the XL 5T: MMU3 slot materials/colours in Connect, `supported-commands` of single-tool printers, START_PRINT tool mapping on MMU/INDX.
- Connect login uses PrusaSlicer's public OAuth client; publishing the plugin needs an own client or Prusa's written consent.

## 22. Slow or unreachable Prusa Connect

- Every action that talks to the printer or Connect runs as a task (`prusa_orca/tasks.py`) on a worker thread; Orca's UI thread never waits on the network. A task has a label, a resource and a deadline: `command` 20 s (Connect `commands/sync` waits for the printer), `job` 15 s, `query` 30 s, uploads none (they report progress). After 4 s a task counts as slow.
- While a task holds a resource, the controls that use it are dimmed with a spinner (bed tile, jog pad, job buttons, sync buttons…) and a second request is refused with "still waiting for the previous request" instead of queued, so a slow Connect never replays stale jog moves. Everything else stays usable.
- The Prusa tab shows a 4 px bar and a pill with the running task at the top ("Setting bed temperature…", turning amber with the elapsed time when slow). A timeout says that the command may still happen. Failures give a readable reason (HTTP 401/409/429/5xx, unreachable, timeout).
- Actions from Orca's Device tab return an error code for a busy resource and report failures and timeouts as Orca warning notifications.
- The status poller fetches Connect on its own thread when PrusaLink answers, so a slow Connect never delays the LAN status. When Connect fails a banner explains that status comes from PrusaLink and tool data may be stale.
- Python can't cancel a blocked request: after a timeout the worker keeps running until the socket timeout (15 s for Connect) and its late answer is logged and dropped.
- Testing: `"debug": {"connect_delay": 25}` or `{"connect_down": true}` in `prusa_local.json` simulates a slow or unreachable Connect. It is read at startup and when settings are saved; remove it and restart Orca to go back to normal.
- A failed read of `supported-commands` is retried after 60 s, not on every page poll.

## 23. Permission prompts for Python's own bytecode cache
Orca points Python's bytecode cache at `<data_dir>/python/pycache` (`PythonInterpreter.cpp`). When a plugin first imports a standard-library module, Python compiles it and writes the `.pyc` through `_write_atomic`, which opens the file by descriptor. The audit hook sees an `open` event with no path, so it can't match the cache folder as an allowed root and asks the user for `FsReadWrite:open` once per module, with no target shown. A grant in `request_permissions()` can't cover it, so the prompts can't be batched.
- The plugin imports everything it needs at load (the logging file handler was the late one), so these writes happen during the plugin's import and not on its first use.
- Upstream fix: don't attribute writes to the interpreter's own bytecode cache to the plugin (e.g. skip `open` events raised from `importlib._bootstrap_external`), or allow fd-based opens of a file created inside an allowed root.
