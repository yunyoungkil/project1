# 13-4C-16 — Focus Style Human Review

## 0. Stage Identity

- Plan: 7
- Version: 13.4
- Stage: 13-4C-16
- Type: Human Visual Review Prototype Preparation
- Target Category: `focus_style`
- Previous Stage: `13-4C-15 — Caption Style Human Approval`
- Canonical Visual Candidate: `CLEAN_DARK_FOCUS`

This stage prepares deterministic visual prototypes for Human Review of `focus_style`.

This stage MUST NOT approve `focus_style`.

This stage MUST end with:

FOCUS STYLE STATUS:
PENDING_VISUAL_REVIEW

HUMAN DECISION:
NONE

This is a prototype/review stage only.

Do NOT persist a Human decision.
Do NOT create an approval row.
Do NOT mutate the canonical visual approval.
Do NOT start Stage 13-5.
Do NOT implement the final renderer.

---

# 1. Current Verified Project Baseline

The completion report from 13-4C-15 states:

Previous canonical id:

10

Current canonical id:

11

Approved categories:

1. font_family
2. background
3. color_palette
4. typography_scale
5. font_weight
6. caption_style

Expected:

APPROVED CATEGORY COUNT:
6

PENDING CATEGORY COUNT:
9

Expected:

focus_style:
PENDING_VISUAL_REVIEW

Expected:

FULL APPROVED VISUAL PROFILE:
NO

READY FOR FINAL RENDERER BINDING:
NO

READY FOR STAGE 13-5:
NO

These values are expectations from the previous completion report.

DO NOT blindly trust them.

Before implementation, query the actual repository / DB state and verify them.

If actual state differs materially:

STOP.

Report the actual state before making changes.

---

# 2. Critical Historical Evidence Rule

Do NOT fabricate Human decisions.

Do NOT claim the user selected a Focus Style candidate.

The user has NOT selected a Focus Style candidate in this stage.

Therefore this stage MUST finish with:

HUMAN DECISION:
NONE

Do NOT use AskUserQuestion to force a Focus Style choice during implementation.

The purpose of this stage is to create review material so the user can inspect it afterward.

A later separate Human Approval stage will persist the user's actual choice.

---

# 3. Source-of-Truth Investigation — REQUIRED BEFORE DESIGN

Before designing Focus Style candidates, inspect the actual project.

Determine from repository evidence:

1. Where `focus_style` is defined or referenced.
2. What semantic elements it is intended to control.
3. Which scene/content roles may use it.
4. Which existing rendering/prototype code already represents focus.
5. Whether focus is:
   - text color,
   - background treatment,
   - border,
   - underline,
   - weight,
   - scale,
   - opacity,
   - glow,
   - marker,
   - or another mechanism.
6. Whether multiple mechanisms already exist.
7. Which palette role(s) are intended for focus.
8. Whether `PRIMARY_FOCUS` is already semantically bound to focus.
9. Whether focus differs from:
   - RELATION
   - SUCCESS
   - EXCEPTION_CAUTION
   - caption_style
   - typography hierarchy
   - answer reveal
10. Whether focus behavior already exists in previous prototype code.
11. Whether actual Plan 7 data contains focus/highlight semantics.
12. Whether Content Blocks, visual roles, scene zones, or other project structures identify focused tokens/elements.

Document the evidence.

Do NOT define the meaning of `focus_style` from general UI/UX knowledge if the project already defines it.

Repository evidence wins.

---

# 4. No Semantic Expansion

This stage approves/reviews ONLY the presentation of an already-defined focus semantic.

Do NOT change:

- which word is focused
- which letter is focused
- which syllable is focused
- when focus occurs
- why focus occurs
- content pedagogy
- teaching sequence
- scene semantics
- Answer Reveal policy
- Content Block semantics

Example:

If existing project data says:

CAP

with `A` as the focused unit,

Focus Style may determine how that existing focus is visually represented.

It MUST NOT decide that `A` should be focused.

Semantic selection and visual styling are separate responsibilities.

---

# 5. Frozen Human-Approved Visual Conditions

All six existing Human-approved categories are fixed conditions.

Focus Style prototypes MUST NOT vary them.

## 5.1 Font Family

APPROVED:

`VERDANA_HUMANIST`

Expected CSS stack:

`Verdana, Geneva, 'Malgun Gothic', sans-serif`

Verify from canonical resolved style.

Do not read the value from an old preview candidate if canonical data exists.

---

## 5.2 Background

APPROVED:

`#111318`

Verify from canonical resolved style.

---

## 5.3 Color Palette

Expected APPROVED palette:

- DEFAULT: `#e6e6e6`
- PRIMARY_FOCUS: `#60a5fa`
- RELATION: `#c4b5fd`
- SUCCESS: `#4ade80`
- SECONDARY: `#9ca3af`
- MUTED: `#757b87`
- EXCEPTION_CAUTION: `#fbbf24`

Verify exact values from canonical resolved style.

Do NOT introduce a new focus color.

Do NOT invent additional palette roles.

---

## 5.4 Typography Scale

Expected APPROVED:

- DOMINANT: 72px
- PRIMARY: 46px
- SUPPORTING: 28px
- CAPTION: 20px
- MICRO: 15px

Verify from canonical resolved style.

---

## 5.5 Font Weight

Expected APPROVED:

BALANCED_HIERARCHY

- DOMINANT: 800 synthetic
- PRIMARY: 700 native
- SUPPORTING: 500 synthetic
- CAPTION: 400 native
- MICRO: 400 native

Verify from canonical resolved style.

Preserve native/synthetic provenance.

---

## 5.6 Caption Style

Expected APPROVED:

BALANCED_INTEGRATED

Expected values:

- text_color_role: DEFAULT
- background: box
- opacity: 0.55
- padding: 8px 16px
- line_height: 1.5

Verify from canonical resolved style.

Do NOT change Caption Style during Focus Style review.

---

# 6. PRIMARY_FOCUS Is a Color Role, Not Automatically a Complete Focus Style

Important architectural distinction:

The approved palette already contains:

PRIMARY_FOCUS = `#60a5fa`

This does NOT automatically prove that the entire `focus_style` should simply be:

`color: #60a5fa`

The palette determines available semantic color.

Focus Style may determine how the focus semantic is visually expressed.

First inspect the actual project contract.

If repository evidence shows focus is strictly color-only, obey that evidence.

If repository evidence allows additional presentation properties, candidate variation may use those properties.

Do NOT invent unsupported properties merely to create visually different candidates.

---

# 7. Candidate Design Principle

After repository investigation, create exactly 3 deterministic Focus Style candidates.

The candidates must differ ONLY in `focus_style`.

Everything already approved must remain identical.

Candidate design should test meaningful levels of visual emphasis.

Conceptually the comparison should answer:

A. Is approved PRIMARY_FOCUS color alone enough?

B. Does the beginner learning context benefit from a moderate additional focus treatment?

C. Does a stronger treatment improve recognition, or does it become distracting?

However, these are conceptual questions only.

Actual candidate properties MUST be derived from project-supported Focus Style dimensions.

Do not force color/background/underline/outline combinations if the project does not support them.

---

# 8. Candidate Naming

Use semantic names rather than arbitrary A/B/C where possible.

Preferred conceptual naming:

1. `COLOR_ONLY`
2. `BALANCED_FOCUS`
3. `STRONG_FOCUS`

But these names are NOT mandatory.

If repository terminology provides better names, use repository terminology.

Names must accurately describe the actual candidate implementation.

---

# 9. Candidate Construction Rules

Each candidate must:

- be deterministic
- use only project-supported Focus Style properties
- use only already-approved palette roles
- preserve approved typography
- preserve approved font weight
- preserve approved background
- preserve approved Caption Style
- preserve identical content
- preserve identical layout
- preserve identical semantic focus target
- preserve identical scene data

The ONLY independent variable must be:

`focus_style`

Add validation proving this invariant where practical.

---

# 10. Do Not Introduce New Palette Roles

Forbidden examples:

- FOCUS_BRIGHT
- FOCUS_BLUE_2
- ACTIVE_BLUE
- HIGHLIGHT_NEON
- BEGINNER_BLUE
- EXTRA_FOCUS

unless such a role already exists in the actual project contract.

Use approved semantic palette roles only.

Most likely the relevant role will be PRIMARY_FOCUS, but VERIFY this.

---

# 11. Avoid Gratuitous Effects

Do NOT introduce effects solely to make candidate 3 visibly stronger.

Examples requiring explicit project support:

- glow
- neon shadow
- blur
- animation
- pulsing
- gradient
- 3D transform
- drop shadow
- stroke
- outline
- scaling
- bouncing

If existing Focus Style architecture does not support them, do not add them.

This stage evaluates the project design system, not arbitrary visual effects.

---

# 12. Focus vs Font Weight

Font Weight is already APPROVED.

Do NOT vary font-weight to simulate stronger focus unless the actual existing `focus_style` contract explicitly includes a focus-specific weight override.

If it does:

document clearly why this does not violate the approved global Font Weight category.

Otherwise:

font weight must remain fixed.

---

# 13. Focus vs Typography Scale

Typography Scale is already APPROVED.

Do NOT make focused text larger merely to produce a stronger candidate unless an existing project contract explicitly supports focus-specific scaling.

If unsupported:

font-size must remain identical across all three candidates.

---

# 14. Focus vs Caption Style

Caption Style was approved in 13-4C-15.

Do NOT use Focus Style review to redesign captions.

Caption boxes must remain:

BALANCED_INTEGRATED

where captions are present.

If focused content appears inside captions in actual project semantics, inspect the architecture carefully.

Do not assume focus overrides caption styling.

Document actual precedence if such interaction exists.

---

# 15. Focus vs Success

`focus_style` and `success_style` are separate pending categories.

Do NOT use SUCCESS color/treatment as a Focus Style candidate.

Focus means the element currently receiving instructional attention.

Success means a correctness/positive-result semantic.

Keep these separate.

Do not pre-approve `success_style`.

---

# 16. Focus vs Relation

RELATION is already an approved palette role.

Do not confuse:

"this is the current thing to look at"

with:

"these two things are related."

If actual prototypes contain both semantics, include at least one useful comparison scene showing they remain distinguishable.

---

# 17. Focus vs Exception/Caution

EXCEPTION_CAUTION is a separate semantic palette role.

Do NOT use caution styling as stronger focus.

If useful and supported by actual Plan 7 data, include a context where focus and caution coexist to verify they remain distinguishable.

Do not fabricate such content if no real project example exists.

---

# 18. Actual Project Content First

Prototype content should reuse actual Plan 7 data whenever possible.

Inspect:

- content blocks
- display_text
- speech assets
- scene plans
- visual roles
- approved/review prototypes
- existing CB06 examples
- actual learning words
- actual Korean instructional text

Prefer real content over invented demo strings.

If actual project data provides:

CAP
BAG
MAP
BAT

or other learning examples, those may be reused if they are actually present.

Do NOT claim a string is actual project content unless verified.

---

# 19. Required Review Contexts

Generate enough contexts to judge Focus Style under realistic conditions.

Target approximately 6 meaningful contexts, provided actual project data supports them.

Recommended categories:

1. `SINGLE_WORD_FOCUS`
   - one word
   - one focused letter/token/segment

2. `MULTI_WORD_LEARNING`
   - several learning words
   - one current focus target

3. `KOREAN_ENGLISH`
   - mixed Korean/English context
   - verify fallback font interaction

4. `DENSE_LEARNING`
   - focus competing with supporting text

5. `RELATION_CONTEXT`
   - PRIMARY_FOCUS vs RELATION distinguishability
   - only if supported by project semantics/data

6. `ANSWER_REVEAL_OR_RESULT_CONTEXT`
   - only if focus legitimately exists in that scene
   - preserve existing Answer Reveal policy

If a recommended context is not supported by actual project data:

Do NOT fabricate semantics just to satisfy the list.

Replace it with another evidence-backed context and explain why.

---

# 20. Side-by-Side Review Is Mandatory

Generate a clear side-by-side comparison page.

Expected filename pattern:

`00_FOCUS_STYLE_SIDE_BY_SIDE.html`

It should show all three candidates under identical content and layout conditions.

Human reviewer must be able to compare:

Candidate 1
Candidate 2
Candidate 3

without mentally switching between unrelated pages.

Also generate individual context pages as appropriate.

---

# 21. Review Index

Generate:

`index.html`

under a dedicated Focus Style review directory.

Expected directory:

`assets/generated/plan_7/render/focus_style_review/`

unless the existing review architecture dictates another path.

Index must clearly explain:

- this is REVIEW ONLY
- focus_style is NOT APPROVED
- Human Decision = NONE
- existing approved categories are fixed
- which property/properties differ between candidates
- what the reviewer should inspect
- candidate names
- links to side-by-side and context prototypes

---

# 22. Manifest

Generate:

`manifest.json`

following existing review-stage patterns.

Manifest should contain enough deterministic metadata to verify:

- Plan
- Stage
- canonical source record
- target category
- current status
- human_decision = null
- candidate definitions
- fixed approved conditions
- prototype files
- source/evidence information where appropriate

Do not invent a new incompatible manifest architecture if prior review stages already define one.

Reuse existing structure.

---

# 23. Candidate Builder

Prefer architecture consistent with prior stages.

Expected conceptual functions may resemble:

`build_focus_style_candidates(...)`

`validate_focus_style_candidates(...)`

`generate_focus_style_review_prototypes(...)`

`run_focus_style_review(...)`

Names may differ if existing project conventions dictate otherwise.

Keep candidate construction as pure/deterministic as practical.

Reuse existing visual-design helpers.

Do NOT create unnecessary parsers.

---

# 24. Validation Requirements

`validate_focus_style_candidates` or equivalent must perform real invariant checks.

At minimum verify:

1. exactly 3 candidates
2. unique candidate names
3. only supported Focus Style properties are used
4. only approved palette roles are referenced
5. no candidate modifies background
6. no candidate modifies font family
7. no candidate modifies global typography scale
8. no candidate modifies global font weights
9. no candidate modifies Caption Style
10. content identical across candidate comparisons
11. semantic focus target identical
12. layout identical
13. hierarchy remains valid where applicable
14. deterministic output

Do not write validation that merely asserts the constants you just constructed.

Test meaningful invariants.

---

# 25. Zero DB Write

This is mandatory.

Before prototype generation:

record:

- visual_design_specs row count
- canonical record ID
- canonical record content
- approved/pending state

After prototype generation:

verify all remain unchanged.

Expected:

canonical id before:
11

canonical id after:
11

But verify actual values.

No new canonical row.

No previous row mutation.

No approval status change.

focus_style remains:

PENDING_VISUAL_REVIEW

---

# 26. approved_visual_profile.json Must Remain Unchanged

This is a Review stage, not Approval.

Therefore:

`approved_visual_profile.json`

must remain byte-identical.

Verify before/after.

If existing architecture unexpectedly requires modification during a Review stage:

STOP and investigate because this would conflict with previous review-stage semantics.

---

# 27. Previous Review Artifacts Must Remain Unchanged

At minimum preserve existing artifacts for:

- font review
- color/background review
- muted color review
- typography scale review
- font weight review
- caption style review

Do not regenerate them.

Do not rewrite their manifests.

Do not alter their revision tags.

Use checksum or byte-level verification where existing tests support it.

---

# 28. Production Assets Must Remain Unchanged

Do NOT modify:

- timeline
- layout
- production scenes
- speech assets
- pronunciation assets
- source_text
- display_text
- active assets
- WAV
- MP4

No production media generation.

---

# 29. CB06 Must Remain Unchanged

Preserve the existing 13-4B-R1 behavior.

Do NOT alter:

- QUESTION/ANSWER policy
- CAPTION visibility
- phase overrides
- scene scope

Focus Style review is visual presentation only.

---

# 30. Renderer Boundary

Renderer remains:

NOT_STARTED

Do NOT:

- implement Remotion
- implement HyperFrames
- choose Remotion vs HyperFrames
- bind the final visual profile
- create production renderer code
- render MP4
- begin Stage 13-5

This stage is renderer-independent Human Review preparation.

---

# 31. CLI

Add a review CLI following established conventions.

Expected form if consistent with previous stages:

`review-focus-style --plan-id 7`

First inspect existing CLI patterns.

Reuse them.

Do NOT create an approval CLI in this stage.

Specifically do NOT add:

`approve-focus-style`

That belongs to a later Human Approval stage after an actual user decision.

---

# 32. Report

Generate a report consistent with prior Human Review stages.

Suggested path:

`reports/focus_style_review_2026-08-21.md`

Use actual current date/project convention if repository naming differs.

Report must clearly state:

FOCUS STYLE HUMAN REVIEW:
READY

FOCUS STYLE STATUS:
PENDING_VISUAL_REVIEW

HUMAN DECISION:
NONE

It must document:

- actual source-of-truth investigation
- what focus_style controls
- what it does NOT control
- candidate definitions
- why candidates differ
- fixed approved conditions
- canonical id before/after
- approved/pending count before/after
- DB zero-write proof
- artifact preservation
- test results
- limitations

---

# 33. Required Negative Cases

Add tests corresponding to actual implementation architecture.

At minimum cover:

CASE A:
canonical visual approval missing → reject review generation

CASE B:
focus_style already APPROVED → reject review generation

CASE C:
required prerequisite category missing → reject

CASE D:
candidate references unapproved palette role → reject

CASE E:
candidate modifies approved font family → reject/invariant failure

CASE F:
candidate modifies approved background → reject/invariant failure

CASE G:
candidate modifies typography scale → reject/invariant failure

CASE H:
candidate modifies global font weight → reject/invariant failure

CASE I:
candidate modifies approved Caption Style → reject/invariant failure

CASE J:
candidate changes semantic focus target → fail

CASE K:
candidate changes content → fail

CASE L:
candidate changes layout → fail

CASE M:
review generation writes DB → fail

CASE N:
review generation changes canonical id → fail

CASE O:
approved_visual_profile.json changes → fail

CASE P:
previous review artifact changes → fail

CASE Q:
source_text/display_text changes → fail

CASE R:
Timeline/Layout/WAV/Pronunciation changes → fail

CASE S:
CB06 visibility/policy changes → fail

CASE T:
external API call occurs → fail

CASE U:
WAV generated → fail

CASE V:
MP4 generated → fail

CASE W:
candidate output nondeterministic → fail

Adapt exact test structure to existing project patterns.

Do not add brittle tests merely to satisfy lettering.

---

# 34. Determinism

Run Focus Style prototype generation twice against identical inputs.

Verify deterministic:

- candidate definitions
- manifest
- prototype HTML
- report-relevant structured values

If timestamps are intentionally present in established architecture, isolate them appropriately rather than pretending byte-level determinism where architecture does not guarantee it.

Report exactly what was compared.

---

# 35. Browser Limitation

Do NOT claim actual browser rendering was visually verified unless it was.

Generated HTML correctness is not equivalent to Human visual approval.

If automated environment cannot perform literal browser visual inspection, state:

- prototypes generated
- structural invariants validated
- actual Human visual judgment pending

Do not claim pixel-perfect rendering.

---

# 36. Korean Fallback Verification

Include at least one Korean + English prototype if actual project content supports it.

Purpose:

verify the already-approved font stack interaction:

Verdana
→ Geneva
→ Malgun Gothic
→ sans-serif

Do NOT claim browser font fallback was definitively proven merely because CSS contains the stack.

Distinguish:

CSS configuration verification

from:

actual browser font-face rendering verification.

---

# 37. Test Baseline

Previous completion report states:

1000 passed / 0 failed

Treat this only as reported historical state.

Establish actual current baseline before implementation.

After implementation run:

1. new Focus Style tests
2. relevant visual design tests
3. full regression suite

Final report must include:

- actual baseline
- new test count
- modified existing test count
- total passed
- failed
- warnings
- regressions

Do not report tests that were not actually run.

---

# 38. README

Modify README only if needed.

Expected minimal change:

add:

`review-focus-style --plan-id 7`

to the Human Review CLI list.

Do NOT claim Focus Style is approved.

Do NOT change full-profile readiness to YES.

---

# 39. PROJECT_STATE

Update PROJECT_STATE.md with verified facts only.

Expected after successful Review preparation:

Current Sub-stage:
13-4C-16

Canonical visual approval:
unchanged

Expected canonical id:
11

Approved:
6

Pending:
9

focus_style:
PENDING_VISUAL_REVIEW

Human Decision:
NONE

Add the three Focus Style review candidates and review artifact location.

Do NOT record any candidate as selected.

Do NOT start Stage 13-5.

---

# 40. Git Safety

The repository may contain accumulated uncommitted changes from prior stages.

Do NOT:

- revert unrelated files
- reset
- clean
- stash
- checkout over changes
- delete prior work
- commit
- push

unless explicitly requested by the user.

Preserve existing working tree state.

At completion report git status accurately.

---

# 41. External Calls

Expected:

Gemini:
0

YouTube:
0

Video AI:
0

Image AI:
0

Font Network:
0

Do not perform external API/network calls.

---

# 42. WAV / MP4

WAV GENERATED:
NO

MP4 GENERATED:
NO

This stage requires neither.

---

# 43. Human Review Output

At the end of the generated review artifacts, present exactly four Human Review choices conceptually:

1 = <actual candidate 1>
2 = <actual candidate 2>
3 = <actual candidate 3>
4 = 세 후보 모두 부적절 — 새 후보 필요

Do NOT preselect one.

Do NOT write:

recommended

best

preferred

approved

winner

unless purely describing prior evidence and not selecting the Focus Style candidate.

The Human must decide after inspecting the prototypes.

---

# 44. Final Console / Report Output

At successful completion output something equivalent to:

FOCUS STYLE HUMAN REVIEW: READY

FOCUS STYLE STATUS:
PENDING_VISUAL_REVIEW

HUMAN DECISION:
NONE

CANONICAL VISUAL CANDIDATE:
CLEAN_DARK_FOCUS

CANONICAL RECORD:
<actual>

FIXED APPROVED CATEGORIES:
- font_family
- background
- color_palette
- typography_scale
- font_weight
- caption_style

FOCUS STYLE CANDIDATES:

1 = <actual candidate name>
    <actual properties>

2 = <actual candidate name>
    <actual properties>

3 = <actual candidate name>
    <actual properties>

4 = 세 후보 모두 부적절 — 새 후보 필요

APPROVED CATEGORY COUNT:
<actual>

PENDING CATEGORY COUNT:
<actual>

FULL APPROVED VISUAL PROFILE:
NO

READY FOR FINAL RENDERER BINDING:
NO

READY FOR STAGE 13-5:
NO

RENDERER:
NOT_STARTED

REVIEW FIRST:
assets/generated/plan_7/render/focus_style_review/index.html

TEST BASELINE:
<actual>

TEST RESULT:
<actual>

EXTERNAL API CALLS:
Gemini <actual>
YouTube <actual>
Video AI <actual>
Image AI <actual>
Font Network <actual>

WAV GENERATED:
NO

MP4 GENERATED:
NO

GIT COMMIT:
NO

GIT PUSH:
NO

NEXT:
Human reviews the Focus Style candidates.
Do not persist Focus Style approval before the Human decision.
Do not start Stage 13-5.

---

# 45. Completion Report

Return:

## 13-4C-16. Focus Style Human Review — 완료 보고

Include:

1. modified/added files
2. actual source-of-truth investigation result
3. exact project meaning of focus_style
4. what focus_style does NOT control
5. baseline canonical id
6. canonical id before/after
7. DB row count before/after
8. approved/pending count before/after
9. existing six approved categories preserved
10. exact fixed approved values
11. actual Focus Style candidate names
12. exact candidate properties
13. rationale for each candidate based on repository evidence
14. proof that only focus_style varies
15. actual Plan 7 content used in prototypes
16. prototype contexts
17. number of generated HTML files
18. side-by-side file
19. index path
20. manifest path
21. Human Decision = NONE
22. focus_style remains PENDING_VISUAL_REVIEW
23. approved_visual_profile.json unchanged
24. previous review artifacts unchanged
25. CB06 unchanged
26. Timeline unchanged
27. Layout unchanged
28. WAV unchanged
29. Pronunciation unchanged
30. source_text/display_text unchanged
31. active assets unchanged
32. validation implementation
33. negative case results
34. determinism result
35. Korean fallback verification scope/result
36. browser verification limitation
37. test baseline
38. new tests
39. modified existing tests
40. final test result
41. regressions
42. external API call counts
43. WAV generated YES/NO
44. MP4 generated YES/NO
45. README modified YES/NO + reason
46. PROJECT_STATE modified YES/NO + details
47. git commit YES/NO
48. git push YES/NO
49. unresolved critical issues
50. unresolved non-critical limitations
51. Full Approved Visual Profile YES/NO
52. Ready for Final Renderer Binding YES/NO
53. Ready for Stage 13-5 YES/NO
54. Renderer status
55. exact file Human should open first
56. four Human Review choices
57. next stage boundary
58. whether every success condition was satisfied

---

# 46. Final Success Criteria

This stage is complete only if:

- actual repository focus semantics were investigated first
- no Human decision was fabricated
- exactly 3 meaningful deterministic candidates were generated
- only focus_style varies
- all six Human-approved categories remain fixed
- actual project content is reused where possible
- useful review contexts exist
- side-by-side comparison exists
- index exists
- manifest exists
- Human Decision remains NONE
- focus_style remains PENDING_VISUAL_REVIEW
- DB receives zero writes
- canonical record remains unchanged
- approved_visual_profile.json remains unchanged
- previous review artifacts remain unchanged
- CB06 remains unchanged
- production data remains unchanged
- no external API calls occur
- no WAV is generated
- no MP4 is generated
- regression suite passes
- PROJECT_STATE accurately reflects Review-ready state
- Stage 13-5 is NOT started
- Renderer remains NOT_STARTED

If any critical invariant fails:

STOP.

Do not convert this Review stage into an Approval stage.

Report the exact failure and evidence.