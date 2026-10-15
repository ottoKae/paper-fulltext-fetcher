# Browser capability boundaries and interrupted downloads

Read this before browser-assisted acquisition. It applies to the host the user calls Ponytail and to other hosts. Ponytail is not a required package or a documented API in this repository. Do not invent an import, executable, tool name or permission based on that label. Use the tool documentation exposed in the current session. A skill cannot add a capability or override a tool's safety rules.

## 1. Select the supported path

Record the available path in the private run receipt. Do not infer availability from a previous session.

| Path | Required evidence | Boundary |
|---|---|---|
| Local saved file | Actual inbox, unique bibliography record, stable PDF | Import and audit need no browser. This is the fallback for user-saved files. |
| Official HTTP/OA/API | Approved source, permitted host, required entitlement | Independent of browser login. Metadata availability is not full-text access. |
| Supported browser connector | Current documentation, returned tab, reliable URL and page state | Use observed controls. Stop on challenge, ambiguity or tool safety denial. |
| Supported Windows computer-use tool | Current documentation and one returned target window | Window discovery does not prove that page capture or input is allowed. Observe, act once, refresh. |
| Repository loopback bridge | Explicit user consent, existing configured session, current tool rules permit it | Optional existing-session attachment only. Not a recovery route around a connector's safety stop. |

If a connector is simply absent, select another permitted path. If it reports a safety stop, obey the stated scope immediately. For example, inability to establish the browser URL safely is not permission to inspect or click that page through a lower-level channel. A user confirmation does not disable the tool's safety checks.

Do not discover credentials, read Cookie stores, inspect browser caches to extract protected PDF bytes, replay signed URLs or solve challenges. Do not use UI automation to enter terminal commands. Do not start a second profile to evade a failure. Read the installed computer-use skill before using its APIs; this reference does not replace its documentation.

## 2. Run one complete smoke acquisition

1. Select one missing record and its observed article page. Confirm the permitted source and the real download directory.
2. Check article identity, institutional recognition and any challenge. Library login alone does not establish publisher entitlement.
3. Use one exact visible PDF control. Observe the result before another action.
4. If a viewer opens, distinguish delivery from saving. Use its visible save control only when the tool permits and supports that action. Observe the resulting dialog and focus before entering a file path. Never reuse coordinates or indexes from an earlier state.
5. Run `workflow browser-receive` preview, then execute. If a file was saved separately, omit `--target`, `--label` and `--allow-browser`; do not click the article again.
6. Verify the final source hash, identity and audit result. Only then schedule a serial batch using the same working path, with the required per-paper delay.

If one bounded save attempt yields no matching file, record the viewer limitation. Ask the user once to save the original PDF into the configured inbox. Include the title or DOI, directory and completion reply. Do not repeatedly ask for login when access is already observed. Saving a file is not participation in eligibility screening.

## 3. Stop at the correct layer

| Observation | Required action |
|---|---|
| HTTP 401/403/418/429, challenge or explicit denial | Pause the affected source/channel. Use the existing evidenced one-test recovery procedure, not repeated requests. |
| Tool safety stop or user stops computer use | Stop inputs within the stated scope. Stop the job's own browser controller/children when necessary. Do not kill the user's browser or unrelated processes. Do not switch input channels. |
| Viewer visible, no saved PDF | Record `watch_timeout` or `manual_required` as supported by the current backend. Use local receive after user saving. Do not infer non-subscription. |
| File saved but wrapper timed out | Check the file and backend receipt before a retry. Preserve both the process timeout and any verified successful transfer. |
| HTTP 200 but identity check fails | Keep the record missing pending diagnosis. Check extraction, language and bibliography; do not assume a wrong paper solely from the validator label. |
| Process interrupted or lock remains | Confirm the owning process stopped, inspect receipts and audit saved files. Review a stale lock before removing it. Do not clear stopped routes automatically. |

Host/channel route events describe acquisition transport. They are not a replacement for host-tool safety restrictions. Do not send tool safety failures to `workflow route recover` as if they were publisher network errors. The existing CLI has no global tool-safety-stop or setting-restoration command; maintain these facts in the private execution receipt.

Independent lawful OA work may continue only when the stop's scope permits it. If the tool requires ending the turn, save local progress and report the stop. Do not promise background work unless an actual allowed process remains active.

## 4. Bound time without losing successful files

Set a finite limit for page loading, transfer, receive and the supervising process. Size the supervisor budget for the whole child command: startup, browser observation, configured watch/transfer time, import, audit and any post-transfer delay. `--wait-seconds` bounds the receiver's watch loop; it is not the total runtime of the command. Use the current CLI help for supported options.

If the supervisor interrupts, terminate only its own child tree when needed and record the stage. Reconcile the filesystem and backend receipts before writing a route failure or relaunching. A validated file saved before interruption remains a successful acquisition; a `.part` file or open viewer does not. Append a correction receipt with evidence hashes instead of rewriting history. An identity check remains necessary even when the expected filename exists.

## 5. Avoid temporary settings as a default workaround

Prefer an observed save control or user saving. Changing PDF preferences, extensions, proxies or profiles is a separate action, not implied by a download request. Current tool prohibitions still apply even with user approval.

If an allowed temporary change is separately approved, first record the exact setting, original value, scope, evidence and restoration method. Do not start the change without a permitted restoration path. Verify both the change and restoration through fresh state. Restore on completion, interruption or cancellation when permitted. Do not change unrelated settings.

If a later safety stop prevents restoration, do not bypass it to clean up. Record `restoration_pending` in the execution receipt and tell the user the exact setting and original value. A restoration request is not a verified restoration. Do not make another dependent change until the pending state is resolved.

## 6. Reconcile and publish one checkpoint

Freeze the requested queue, record IDs, bibliography hash and baseline count. For later checkpoints use one stable copy of the audit. Verify that downloaded + missing equals the frozen total and that each counted local file matches its audit hash. Distinguish batch additions from cumulative additions. Publisher names can be incomplete; use DOI prefixes as queue hints, not proof of source ownership or access.

Keep the per-record acquisition status separate from eligibility and conversion status. Acquisition of all candidates must not silently run a pilot or fill reviewer decisions. Successful Docling parsing also does not establish study eligibility.

For multilingual or image-only PDFs, inspect the actual front pages and extraction result under [manual import](manual-import.md). A Latin-token matcher can reject a correct Chinese title. Terminal encoding noise can misrepresent intact UTF-8 metadata. Do not rewrite source titles or reduce identity thresholds to force acceptance. Do not assume the HTTP backend retained a rejected `.part`; consult its receipt and preserve available inbox originals. Record the actual actor for any visual approval; never label AI inspection as independent human review.

At a pause report: timestamp and input hash, verified count, missing count, exact blocking step, saved receipt location, temporary settings state and next allowed action. File acquisition is complete only when every requested record has verified full text, or when the user accepts an explicitly incomplete result. Never promise exhaustive discovery from a finite candidate queue.
