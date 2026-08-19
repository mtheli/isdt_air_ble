# Releasing

How a release is cut and, more importantly, how its notes are written. The
format is shared with the sibling integrations (philips_sonicare_ble,
philips_shaver) — this file exists so it stops drifting.

## Release notes

Written for someone who runs the integration, not for someone who reads the
diff. What changed for them, and what they have to do about it.

**Structure:** `##` sections by theme, each holding bullets that open with a
bold phrase and then explain themselves in one or two sentences.

```markdown
## Ghost entities on the A8 Air

Optional lead-in paragraph — only when the bullets need context to make
sense, e.g. an external cause the reader could not know about.

- **Setup removes registry entries the detected model cannot provide** —
  cell-voltage sensors on models without per-cell data, and channel or
  slot entities beyond the model's slot count.
- **Entities the model actually provides are untouched** — names, history
  and enabled/disabled state stay as they are.
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
