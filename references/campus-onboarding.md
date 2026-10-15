# Campus onboarding and closed-loop acquisition

## 1. Configure the user, not a particular university

Ask only for missing institution/access mode, bibliography/workspace and existing browser/download directory. In private `acquisition.local.toml`, configure `[institution].domains`, `authentication_domains`, and `network_mode` (`campus`, `institution_vpn`, `carsi`, `public`, or `unspecified`). Set `[browser].downloads_dir` to the actual download directory. Absolute paths are accepted locally and are not printed in diagnostic reports. The default is the workspace's private inbox, not an assumed OS Downloads folder.

`doctor --config ... --output ...` checks dependencies, local paths and configured domains. Optional `--clash-config` reads rule text without changing it or exposing proxy nodes/subscription URLs. Its domain matches are hints only: policy order, rule providers, TUN, external VPN and current egress can change the actual route. No rule match or offline success proves campus entitlement. An absent institution configuration is unknown, not an inferred default university.

## 2. Verify the access layers separately

1. Confirm the selected access mode actually reaches the institution service.
2. Inspect the publisher article page for institutional recognition and access to the requested paper.
3. Test its actual PDF delivery, which can use a different asset host.
4. Confirm the file was saved and passes identity/container/hash validation.

Clash is optional. With campus-IP access, relevant hosts may need the campus egress; off-campus direct access is not a substitute for a school VPN or CARSI. Propose only evidence-based narrow changes, obtain confirmation and preserve original values. Do not turn every publisher domain into a universal DIRECT rule. Institution web access is not an API/TDM entitlement.

## 3. Existing browser, explicit consent

Read [tool capability boundaries](browser-capabilities.md) before browser work. Use the user's existing authenticated browser. Login, MFA and challenges remain user actions. Prefer a currently available supported browser connector. An optional fallback attaches to a user-configured loopback CDP endpoint only when current tool rules permit it; it does not launch a browser, inspect Cookie stores, change settings or expose debugging to the LAN. Configure `[browser].cdp_endpoint` privately only when this fallback is requested. An unavailable connector may justify another permitted path; a tool safety stop must not be bypassed by this fallback.

```powershell
& .\scripts\run.ps1 workflow browser-probe --config ..\my-review\acquisition.local.toml --allow-browser --allow-host publisher.example --output ..\my-review\browser-probe.json
```

This example host is a placeholder, not a real test target. Probe outputs only matching visible tabs and stripped URLs. A connected endpoint does not establish login. Use observed target IDs and exact visible PDF control labels, never guessed IDs, signed URLs or fixed screen coordinates.

After locating the intended tab, add `--target OBSERVED_ID` to perform a read-only page inspection. This can record institutional recognition or an existing challenge without clicking a download, navigating or changing authentication. Use a new output filename to preserve each observation.

## 4. Close the file loop

```powershell
& .\scripts\run.ps1 workflow browser-receive --config ..\my-review\acquisition.local.toml --record-id RECORD_ID
& .\scripts\run.ps1 workflow browser-receive --config ..\my-review\acquisition.local.toml --record-id RECORD_ID --execute
```

The first invocation previews only. The second watches the configured inbox for at most 90 seconds by default, checks stable size/mtime across polls, rejects unmatched files, stages a hashed copy, performs Skill import dry-run/import and final audit. `--inbox` overrides the download location; `--wait-seconds` has a 300-second upper bound. Unrelated files and partial `.crdownload`/`.part` files are not imported. The original saved file is retained. A valid existing corpus file is skipped without another browser click.

To assist with one already-open article, add `--target OBSERVED_ID --label "OBSERVED PDF LABEL" --allow-browser --allow-host ACTUAL_HOST`. The bridge checks the article identity and page state before clicking; ambiguous controls stop. It does not solve challenges, implement site-specific URL workarounds or save every native/Adobe viewer. A separately available, permitted UI tool may operate an observed viewer save control. If that path is unavailable or one bounded attempt produces no file, ask the user to save the original PDF into the configured directory. After saving, use the local-only commands above without a browser target. Do not repeat the failed article click. This is not a successful download until import/audit passes.

Each execution creates immutable `outputs/acquisition/browser-runs/<run>/` receipts and before/after audits. After success, the `outputs/acquisition/audit/` latest view is refreshed for existing corpus commands. Run only against an active workspace, never a sealed review snapshot. One receiver per workspace is enforced by a lock; after a hard interruption, confirm the process has stopped before removing its stale lock. Do not clear locks or stopped routes speculatively.

## 5. Stops and recovery

`fetch-verified` persists HTTP-route stops. Browser receivers persist detected browser-route stops. Existing manual acquisition through another connector must record observed stops using `workflow route stop --config ... --host ... --channel browser --reason challenge_or_block --evidence FILE`.

Use `workflow route status` to inspect a route. A 401/403/418/429, challenge or explicit denial stops the affected source/channel; it is not silently cleared by restarting the helper. An interrupted in-flight attempt also needs review. Local viewer/save timeouts are not labeled non-subscription. Independent OA repositories remain separate lawful sources, not a way to replay blocked URLs.

A tool safety stop is not a publisher route error. Obey its scope, stop affected browser jobs and do not use route recovery to override it. After any interruption inspect saved files before relaunching: a successful transfer can precede a supervisor timeout during import, audit or cooldown. Keep that process outcome distinct from the validated file outcome. Budget the whole command, not just `--wait-seconds`.

Only after the user actually restores access or a transient failure has a fresh recovery basis, run `workflow route recover --config ... --host ... --channel browser --evidence FILE --user-confirmed`. This records the evidence hash and permits one test. The same evidence cannot repeatedly reopen a route. A started probe consumes authorization; a new challenge pauses again. Only successful file validation establishes acquisition. Metadata API success does not restore a PDF route.

Keep the original recovery evidence file with the private project: route events retain its basename and hash, not its potentially sensitive contents. Before authorizing recovery of an interrupted attempt, confirm its process has stopped; authorization may release a stale route lock.

## 6. Generalize examples conservatively

Past examples demonstrated that an authenticated browser can work when a separate HTTP client fails; a new PDF tab can still be unsaved; and a default download directory can differ from an assistant inbox. These are reusable diagnostics, not guarantees for any publisher or school. Publisher-specific attachment links must be observed/documented for that page; never invent `download=true` variants. Temporary PDF-viewer preferences are not a default workaround. They require separate approval, a permitted tool and a verified restoration plan; this helper does not change them. If a safety stop prevents restoration, record the pending original value and give the user precise restoration instructions instead of bypassing the stop.
