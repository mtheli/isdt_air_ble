# Releasing

How a release is cut and, more importantly, how its notes are written. The
format is shared with the sibling integrations (philips_sonicare_ble,
philips_shaver) — this file exists so it stops drifting.

## Release notes

Written for someone who runs the integration, not for someone who reads the
diff. What changed for them, and what they have to do about it.

**Written in English.** The integration is localized, the notes are not — one text
every reader can open beats a partial set of translated ones. German belongs
in the German-language forum threads, where a release gets announced in the
reader's own language; the notes themselves stay English.

**One section per feature.** The bullets underneath carry the details. If it is
not obvious who a feature applies to, say so in one line under the heading.

**One sentence per bullet,** opening with two to five bold words that run into
the sentence. No labels, no whole sentence in bold. Write what the user sees,
with the previous behaviour as a short trailing clause where one is needed.

**Plain language.** No literary voice, no marketing tone, no idiom where a verb
will do. This holds for commit messages too. Reasoning belongs in the commit
message, not in the notes.

**No hard line breaks.** GitHub renders a single newline as a line break and
tears prose apart mid-sentence. One paragraph, one line.

```markdown
## Last session

Two new sensors, Last Session and Last Session Duration. On brushes with the storage service and on the Sonicare for Kids, not on the 7100 (HX742X).

- **The state is the start time** of the session, the attributes hold duration, routine, mode and intensity.
- **Sessions brushed without a connection** are read on the next one.
- **Sessions the brush cannot date** are skipped.

---

📟 **No ESP bridge firmware change** — `MIN_BRIDGE_VERSION` stays 1.4.0.
```

**Title:** `vX.Y.Z — what it is about`, e.g.
*v0.9.3 — remove ghost cell-voltage entities on the A8 Air*.

**What does not belong in the notes:** commit lists, file names, internal
symbol names, test tallies, and documentation-only changes.

**Credit belongs in the notes.** Name whoever reported the problem, tested
the fix or supplied the logs, with `@handle` and the issue number, in the
bullet their work belongs to. The `@` is not decoration: it notifies them
and links their profile, and it is how the release and the issue thread
explain each other.

When an external change caused the release, link it. A reader who upgraded
Home Assistant and then saw something break deserves to know the two are
connected — link the core pull request or release that changed the
behaviour.

## Cutting the release

1. Content commits first, pushed and green.
2. `custom_components/isdt_air_ble/manifest.json` — new integration
   version, as its own commit: `release: vX.Y.Z`.
3. Tag `vX.Y.Z`, push, then `gh release create` with the notes above.
