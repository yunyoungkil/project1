# 13-4C-15 — Caption Style Human Approval

## 0. Stage Identity

- Plan: 7
- Version: 13.4
- Stage: 13-4C-15
- Type: Human Visual Approval Persistence
- Target Category: `caption_style`
- Previous Stage: `13-4C-14 — Caption Style Human Review`
- Canonical Visual Candidate: `CLEAN_DARK_FOCUS`

This stage persists the user's actual Human Review decision for Caption Style.

This is NOT a new prototype-generation stage.
This is NOT a redesign stage.
This is NOT Stage 13-5.
Do NOT start final renderer binding.

---

# 1. Actual Human Decision

The user has now actually reviewed the Caption Style prototypes and made a Human Review decision in the current conversation.

Actual user statement:

> "2번으로 하자"

Candidate mapping from 13-4C-14:

1 = `MINIMAL_TEXT`
2 = `BALANCED_INTEGRATED`
3 = `BEGINNER_EMPHASIS`
4 = all candidates rejected / new candidates required

Therefore:

HUMAN DECISION:
`BALANCED_INTEGRATED`

This is a real Human Review decision.

Do NOT reinterpret it.
Do NOT ask the user to choose again unless repository evidence shows that the candidate mapping above does not match the actual 13-4C-14 implementation/artifacts.

Before persisting anything, verify the mapping from the actual repository implementation / generated manifest.

If repository evidence contradicts this prompt, STOP and report the contradiction instead of guessing.

---

# 2. Selected Caption Style

Persist the Human-selected Caption Style candidate:

`BALANCED_INTEGRATED`

Expected exact candidate values from 13-4C-14:

- text_color_role: `DEFAULT`
- background: `box`
- opacity: `0.55`
- padding: `8px 16px`
- line_height: `1.5`

These values MUST be verified against the actual 13-4C-14 candidate definition before persistence.

Do not trust this prompt alone if repository state differs.

---

# 3. Critical Source-of-Truth Rule

Before writing:

1. Read the actual current canonical visual approval from DB.
2. Read the actual `BALANCED_INTEGRATED` definition from the 13-4C-14 implementation.
3. Read the generated Caption Style review manifest if present.
4. Confirm:
   - canonical record is the expected current record
   - `caption_style` is still `PENDING_VISUAL_REVIEW`
   - candidate 2 is actually `BALANCED_INTEGRATED`
   - its exact values match the generated review artifacts
   - previously approved categories remain APPROVED

Do not manufacture missing evidence.

If any required invariant fails:

STOP.

Do not write a new canonical row.

Report the exact mismatch.

---

# 4. Expected Pre-Approval State

Expected state after 13-4C-14:

Canonical record id:

`10`

Expected approved categories:

1. `font_family`
2. `background`
3. `color_palette`
4. `typography_scale`
5. `font_weight`

Expected:

APPROVED CATEGORY COUNT = 5

Expected pending:

`caption_style = PENDING_VISUAL_REVIEW`

Expected total:

PENDING CATEGORY COUNT = 10

These are expectations only.

Verify them from actual repository/DB state.

---

# 5. Previously Approved Values Are Frozen

This stage MUST NOT modify any previously approved Human Review value.

Expected frozen values:

## Font Family

`VERDANA_HUMANIST`

CSS stack:

`Verdana, Geneva, 'Malgun Gothic', sans-serif`

Native Verdana weights known by the project:

`[400, 700]`

Do NOT reinterpret synthetic weights as native faces.

---

## Background

`#111318`

---

## Color Palette

- DEFAULT: `#e6e6e6`
- PRIMARY_FOCUS: `#60a5fa`
- RELATION: `#c4b5fd`
- SUCCESS: `#4ade80`
- SECONDARY: `#9ca3af`
- MUTED: `#757b87`
- EXCEPTION_CAUTION: `#fbbf24`

---

## Typography Scale

- DOMINANT: `72px`
- PRIMARY: `46px`
- SUPPORTING: `28px`
- CAPTION: `20px`
- MICRO: `15px`

---

## Font Weight

Human-approved candidate:

`BALANCED_HIERARCHY`

Exact weights:

- DOMINANT: `800` synthetic
- PRIMARY: `700` native
- SUPPORTING: `500` synthetic
- CAPTION: `400` native
- MICRO: `400` native

These values must remain unchanged.

---

# 6. Caption Style Approval to Persist

Human-selected candidate:

`BALANCED_INTEGRATED`

Expected exact resolved values:

```text
text_color_role = DEFAULT
background = box
opacity = 0.55
padding = 8px 16px
line_height = 1.5