# 13-4C-18 — Success Style Human Review

## 0. Stage Identity

- Plan: 7
- Version: 13.4
- Stage: 13-4C-18
- Type: Human Visual Review Prototype Preparation
- Target Category: `success_style`
- Previous Stage: `13-4C-17 — Focus Style Human Approval`
- Canonical Visual Candidate: `CLEAN_DARK_FOCUS`

This stage prepares deterministic Human Review prototypes for `success_style`.

This stage MUST NOT approve `success_style`.

This stage MUST end with:

SUCCESS STYLE STATUS:
PENDING_VISUAL_REVIEW

HUMAN DECISION:
NONE

Do NOT persist approval.
Do NOT create a new canonical approval row.
Do NOT modify `approved_visual_profile.json`.
Do NOT start Stage 13-5.
Do NOT implement or choose the Renderer.

---

# 1. Read PROJECT_STATE First

Before making any code change:

read:

`PROJECT_STATE.md`

Use it for orientation only.

Then verify current state against actual canonical sources.

Source-of-truth precedence:

1. canonical DB
2. canonical machine-readable artifacts
3. current repository code
4. PROJECT_STATE.md
5. review artifacts / reports
6. README
7. this prompt's expected values

If PROJECT_STATE conflicts with canonical DB/artifacts:

canonical state wins.

If the discrepancy is material to this stage:

STOP and report it.

---

# 2. Expected Current State — Verify, Do Not Assume

Previous completion report says:

Canonical record:
12

Approved:
7

Pending:
8

Expected APPROVED categories:

1. font_family
2. background
3. color_palette
4. typography_scale
5. font_weight
6. caption_style
7. focus_style

Expected:

success_style:
PENDING_VISUAL_REVIEW

Expected:

FULL APPROVED VISUAL PROFILE:
NO

READY FOR FINAL RENDERER BINDING:
NO

READY FOR STAGE 13-5:
NO

RENDERER:
NOT_STARTED

These are expected values only.

Query actual state.

Do not hardcode the record ID or counts into implementation logic.

---

# 3. Human Decision Rule

There is NO Human Decision for Success Style yet.

The user has not reviewed Success Style candidates.

Therefore:

HUMAN DECISION:
NONE

must remain true throughout 13-4C-18.

Do NOT infer a Success Style choice from:

- previous numeric choices
- focus_style choice
- caption_style choice
- color palette approval
- prior "1", "2", "3"
- previous visual preference
- prior prompts/reports

Do NOT ask for approval during this implementation stage.

The purpose is to generate review artifacts only.

---

# 4. Investigate the Actual Meaning of `success_style`

Before designing candidates, inspect the actual repository.

Determine what `success_style` is supposed to style in this project.

Search:

- `success_style`
- `SUCCESS`
- `ANSWER_REVEAL`
- `ANSWER_CONFIRMATION`
- `MINI_SUCCESS`
- `answer`
- `correct`
- `success`
- `reveal`
- `color_role`
- `entrance_style`
- `CB06`
- `scene_visual_rules`
- `element_states`
- `motion_bindings`
- `color_bindings`
- `typography_bindings`
- `caption_bindings`
- previous prototypes/reports/tests

At minimum answer:

1. Which scene(s) actually use SUCCESS?
2. Which element/zone gets SUCCESS?
3. Does Plan 7 use SUCCESS only for ANSWER?
4. Does CB06 use SUCCESS in ANSWER_CONFIRMATION?
5. Does success_style currently exist anywhere in code?
6. Is success currently expressed only by color?
7. Are there existing box/border/underline/marker semantics?
8. Does Answer Reveal already use a separate entrance/motion semantic?
9. Which responsibilities belong to `success_style` vs `motion_style`?
10. Does success_style affect content semantics or only presentation?

Do not invent a generic "correct answer UI" if the project already defines something narrower.

Repository evidence wins.

---

# 5. Preserve Success Semantics

This stage reviews PRESENTATION only.

Do NOT change:

- what the correct answer is
- when answer reveal happens
- barrier timing
- not_before_ms
- pause duration
- viewer_action
- ANSWER visibility
- prompt visibility
- scene timing
- production content
- source_text
- display_text
- active asset

Example:

If CB06 says:

ANSWER is hidden until the reveal barrier

and later becomes visible,

success_style can control how the visible successful answer looks.

It MUST NOT change when that answer becomes visible.

---

# 6. Frozen Approved Conditions

All 7 approved categories are fixed.

Success Style candidates MUST NOT vary any of them.

## Font Family

APPROVED:
VERDANA_HUMANIST

Expected stack:
`Verdana, Geneva, 'Malgun Gothic', sans-serif`

Verify from canonical state.

## Background

APPROVED:
`#111318`

## Color Palette

APPROVED:

- DEFAULT `#e6e6e6`
- PRIMARY_FOCUS `#60a5fa`
- RELATION `#c4b5fd`
- SUCCESS `#4ade80`
- SECONDARY `#9ca3af`
- MUTED `#757b87`
- EXCEPTION_CAUTION `#fbbf24`

## Typography Scale

APPROVED:

- DOMINANT 72px
- PRIMARY 46px
- SUPPORTING 28px
- CAPTION 20px
- MICRO 15px

## Font Weight

APPROVED BALANCED_HIERARCHY:

- DOMINANT 800
- PRIMARY 700
- SUPPORTING 500
- CAPTION 400
- MICRO 400

## Caption Style

APPROVED BALANCED_INTEGRATED:

- text_color_role = DEFAULT
- background = box
- opacity = 0.55
- padding = 8px 16px
- line_height = 1.5

## Focus Style

APPROVED COLOR_ONLY:

Expected:

- color_role = PRIMARY_FOCUS
- highlight_box = False
- box_opacity = 0.0
- padding = 0
- underline = False

Verify all exact values from canonical resolved state.

Do not copy stale preview values.

---

# 7. SUCCESS Color Is Already Approved

Important:

`SUCCESS = #4ade80`

is already Human-approved as a semantic color role.

This stage does NOT review whether green should be changed.

Do NOT create:

- SUCCESS_GREEN_2
- BRIGHT_SUCCESS
- CORRECT_GREEN
- ANSWER_GREEN
- GLOW_GREEN

or any new palette role.

Use the approved SUCCESS role.

success_style determines presentation of the SUCCESS semantic.

---

# 8. success_style Is Not motion_style

Keep these categories separate.

`success_style` should control static/resolved visual treatment.

`motion_style` will later control animation/timing/easing/reveal behavior.

Do NOT make Success Style candidates differ by:

- animation duration
- easing
- bounce
- pulse
- fade-in speed
- scale animation
- motion timing

Those belong to `motion_style`.

Static review HTML is sufficient for this stage.

---

# 9. success_style Is Not focus_style

Focus Style:

"what the learner should currently pay attention to"

Success Style:

"the successfully revealed/correct result"

Do not reuse PRIMARY_FOCUS treatment as Success Style.

Use SUCCESS semantic role where appropriate.

Ensure Focus and Success remain visually distinguishable.

Include at least one context showing both if actual project semantics support it.

---

# 10. success_style Is Not Caption Style

Do not redesign caption boxes.

Caption Style remains fixed.

If a caption is present in Success Style prototypes:

use the approved BALANCED_INTEGRATED caption styling.

Do not use caption box opacity/padding as candidate variables for success_style.

---

# 11. Candidate Design Principle

After repository investigation, create exactly 3 deterministic candidates.

The three candidates must represent meaningful levels of success emphasis.

Conceptual direction:

1. `COLOR_ONLY`
2. `BALANCED_SUCCESS`
3. `STRONG_SUCCESS`

These names are suggestions only.

If repository terminology suggests better names, use those.

Actual properties must be derived from supported project mechanics.

Do not force unsupported styling merely to produce visual variation.

---

# 12. Candidate 1 Philosophy

Candidate 1 should represent the minimum visual success treatment supported by the project.

Likely concept:

SUCCESS color only.

But verify actual architecture.

If success is currently color-only, this can be a valid baseline.

Do not add box/underline/border if this candidate is meant to represent minimal intervention.

---

# 13. Candidate 2 Philosophy

Candidate 2 should represent a balanced, noticeable success treatment.

It should make the correct answer immediately recognizable without turning it into a large UI card.

Potential dimensions ONLY if supported by existing architecture:

- subtle box
- subtle background tint
- underline
- border
- small padding
- marker

But use only project-supported properties.

Do not invent a design vocabulary unsupported by the codebase.

---

# 14. Candidate 3 Philosophy

Candidate 3 should represent stronger beginner-oriented success emphasis.

It must still remain appropriate for repeated use.

Avoid:

- celebration effects
- confetti
- fireworks
- glow
- bounce
- huge scale
- decorative animation

unless such semantics already exist in the project, which is unlikely.

This is a learning confirmation, not a game reward screen.

---

# 15. No Celebration Content

Important project constraint:

Previous CB06 prototype work explicitly verified that celebration text was absent.

Do NOT add:

- Great!
- Correct!
- Well done!
- 정답입니다!
- 잘했어요!
- 🎉
- ✅

unless actual Plan 7 content already contains it.

Success Style cannot invent new copy.

Use the existing answer/content only.

---

# 16. Actual Plan 7 Evidence

Use actual Plan 7 content where possible.

Inspect actual answer assets/content.

Known historical examples may include:

CAP
cap

But verify before use.

Do not claim unverified strings are actual project data.

Use actual CB06/Plan 7 data whenever available.

---

# 17. Required Review Contexts

Generate meaningful contexts supported by the repository.

Target approximately 6 context families.

Recommended:

1. `SINGLE_ANSWER`
   - one revealed answer
   - isolated success presentation

2. `PROMPT_TO_ANSWER`
   - prompt remains as MUTED trace
   - answer is SUCCESS
   - static post-reveal state

3. `FOCUS_AND_SUCCESS`
   - current focus semantic and success semantic visible together
   - only if actual architecture supports coexistence

4. `DENSE_LEARNING`
   - answer plus supporting instructional information

5. `KOREAN_ENGLISH`
   - mixed Korean/English surrounding content
   - no invented celebration text

6. `MULTIPLE_LEARNING_ELEMENTS`
   - demonstrate SUCCESS remains unique against DEFAULT/RELATION/PRIMARY_FOCUS

If a context is unsupported by actual data:

replace it with evidence-backed context.

Do not fabricate scene semantics.

---

# 18. CB06 Is Mandatory Review Evidence

Because existing project evidence shows CB06 Mini Success uses SUCCESS, include CB06-oriented context if verified.

Preserve:

- ANSWER typography semantic
- ANSWER color semantic
- prompt trace
- CAPTION policy
- barrier semantics
- phase structure

Do NOT modify CB06.

Use review-only static reconstruction of post-reveal state where appropriate.

---

# 19. Side-by-Side Is Mandatory

Generate:

`00_SUCCESS_STYLE_SIDE_BY_SIDE.html`

Show candidates 1/2/3 using identical content and layout.

Human reviewer should be able to compare:

- immediacy of answer recognition
- competition with focus text
- readability
- visual noise
- repeated-use comfort
- beginner clarity

All non-success variables must be identical.

---

# 20. Candidate Isolation

The ONLY variable across candidate versions must be `success_style`.

Must remain identical:

- semantic answer target
- content
- source text
- display text
- font family
- font size
- font weight
- background
- palette tokens
- focus style
- caption style
- layout
- spacing outside success_style
- scene content

Validate this where possible.

---

# 21. Avoid motion in static prototypes

Do NOT simulate different motion by changing static end frames.

For example:

Candidate 3 should not be "bigger because it would animate bigger."

Static properties only.

Motion will be reviewed later.

---

# 22. Dedicated Review Directory

Generate under:

`assets/generated/plan_7/render/success_style_review/`

unless existing naming convention dictates otherwise.

Expected contents:

- `index.html`
- `manifest.json`
- `00_SUCCESS_STYLE_SIDE_BY_SIDE.html`
- context × candidate prototype files

Do not modify previous review directories.

---

# 23. index.html

Index should clearly state:

SUCCESS STYLE HUMAN REVIEW

STATUS:
PENDING_VISUAL_REVIEW

HUMAN DECISION:
NONE

FIXED APPROVED CONDITIONS:
all 7 approved categories

CANDIDATES:
actual 3 names and exact properties

Include:

- what success_style means in this project
- what it does NOT control
- which actual Plan 7 scene(s) use SUCCESS
- warning that motion is not being reviewed here
- review links
- Human choice list

---

# 24. Manifest

Create a deterministic manifest consistent with prior review artifacts.

Include:

- review_stage = 13-4C-18
- target_category = success_style
- plan_id
- visual_design_version
- canonical_record_id
- canonical_visual_candidate
- current_status = PENDING_VISUAL_REVIEW
- human_decision = null
- candidates
- exact properties
- fixed approved categories
- evidence scenes/elements
- prototype files
- zero_db_write = true

Reuse existing manifest conventions.

Do not create a new unrelated schema.

---

# 25. Candidate Builder

Prefer pure deterministic functions such as:

`build_success_style_candidates(...)`

`validate_success_style_candidates(...)`

`generate_success_style_review_prototypes(...)`

`run_success_style_review(...)`

Naming may follow actual repository patterns.

Reuse helpers for:

- color resolution
- candidate validation
- HTML review generation
- canonical approval loading
- palette lookup

Do not duplicate logic unnecessarily.

---

# 26. Actual SUCCESS Mapping Verification

Verify actual current visual design logic.

Expected historical behavior:

ANSWER → SUCCESS

But query actual implementation.

If SUCCESS is mapped to other elements/scenes too:

report them.

Do not narrow the project contract based only on this prompt.

If it is used only for ANSWER in Plan 7:

report that clearly.

---

# 27. No New Color Hex

Candidate styles may resolve approved SUCCESS role to:

`#4ade80`

but may not introduce arbitrary new literal colors.

If candidate uses an alpha/tinted background derived from SUCCESS, it must be deterministically derived from the approved role.

Example concept:

rgba(SUCCESS, alpha)

may be acceptable if supported by the candidate architecture.

Do not use an unrelated green hex.

---

# 28. Derived Alpha Is Not a New Palette Approval

If candidate properties include:

box/background opacity

and derive RGBA from SUCCESS,

do not interpret that as creation of a new canonical palette color.

The canonical semantic role remains:

SUCCESS

The alpha treatment belongs to success_style.

Document this distinction.

---

# 29. Static Accessibility Consideration

Check whether selected static treatment risks communicating correctness only through color.

The broader visual system already requires:

color_not_sole_cue.

Therefore candidates should allow Human Review to assess whether success is identifiable through:

- semantic position
- typography hierarchy
- state change
- box/border/underline if supported
- answer label/context

Do not automatically approve based on accessibility heuristics.

But report candidate implications.

---

# 30. Do Not Change Existing Accessibility Contract

Do not rewrite 13-4A `color_not_sole_cue`.

Do not weaken it.

Do not claim Success Style solves accessibility globally.

This is a local Human Review.

---

# 31. Zero DB Write

Critical.

This stage is Review Preparation.

Before run:

capture:

- canonical record
- visual_design_specs row count
- approval states

After run verify:

no change.

Expected canonical:

12

Expected visual_design_specs rows:

12

But verify actual values.

No insert.
No update.
No deletion.

---

# 32. approved_visual_profile.json

Must remain unchanged.

Use byte/hash comparison if established.

A review stage must not change canonical approved state.

---

# 33. Previous Review Artifacts

Must remain unchanged:

- font_review
- color_background_review
- muted_color_review
- typography_scale_review
- font_weight_review
- caption_style_review
- focus_style_review
- original 13-4B-R1 prototypes

Do not regenerate.

---

# 34. Production Invariance

No modifications to:

- production_blocks
- speech_assets
- generated_assets
- render_specs
- render_timelines
- scene_layouts
- source_text
- display_text
- pronunciation data
- active assets
- WAV files
- timeline
- scene layout

---

# 35. Renderer Boundary

Do NOT:

- install HyperFrames
- install Remotion
- choose renderer
- build adapter
- generate production compositions
- generate MP4
- start Stage 13-5

Renderer remains NOT_STARTED.

HyperFrames vs Remotion evaluation stays separate.

---

# 36. CLI

Add only a review command consistent with existing naming.

Expected:

`review-success-style --plan-id 7`

if this matches current CLI conventions.

Do NOT add:

`approve-success-style`

in this stage.

Approval comes after Human review.

---

# 37. Validation

Implement meaningful success candidate validation.

At minimum:

1. exactly 3 candidates
2. unique IDs
3. allowed properties only
4. approved SUCCESS role used
5. no new color roles
6. no unapproved arbitrary colors
7. no changes to font family
8. no changes to typography scale
9. no changes to font weight
10. no changes to focus_style
11. no changes to caption_style
12. identical content
13. identical semantic target
14. identical layout
15. no motion properties
16. deterministic definitions
17. human_decision is NONE
18. success_style remains pending

---

# 38. Required Negative Tests

At minimum:

CASE A:
success_style already APPROVED → reject review

CASE B:
SUCCESS palette role missing → reject

CASE C:
candidate introduces arbitrary hex → reject

CASE D:
candidate references unapproved palette role → reject

CASE E:
candidate changes typography → fail

CASE F:
candidate changes font weight → fail

CASE G:
candidate changes focus_style → fail

CASE H:
candidate changes caption_style → fail

CASE I:
candidate changes semantic answer target → fail

CASE J:
candidate changes reveal timing/barrier → fail

CASE K:
candidate includes motion/easing/duration → reject

CASE L:
candidate adds celebration content → reject/fail invariant

CASE M:
candidate ID duplicate → reject

CASE N:
invalid alpha/opacity → reject

CASE O:
review writes DB → fail

CASE P:
approved_visual_profile changes → fail

CASE Q:
previous review artifacts change → fail

CASE R:
source_text/display_text changes → fail

CASE S:
CB06 timing/visibility changes → fail

CASE T:
WAV generated → fail

CASE U:
MP4 generated → fail

CASE V:
external API call → fail

CASE W:
candidate output nondeterministic → fail

Adapt implementation to existing test conventions.

---

# 39. Determinism

Generate candidates twice from identical canonical input.

Verify candidate definitions identical.

Generate review artifacts deterministically where architecture permits.

If established timestamp behavior prevents byte-identical reports:

separate deterministic structured content from timestamp metadata.

Report exact scope.

---

# 40. Browser Verification Honesty

Do not claim:

"Success Style visually approved"

or:

"browser rendering validated"

during implementation.

The output is:

REVIEW READY

not APPROVED.

Human visual inspection happens after generation.

---

# 41. Actual Korean/English Review

Include mixed Korean/English context if actual project content supports it.

Purpose:

ensure Success Style doesn't overpower:

- Korean instruction
- English word
- caption
- answer

Do not claim fallback rendering is definitively validated unless actual browser rendering is inspected.

---

# 42. Test Baseline

Previous report:

1035 passed

Treat as historical only.

Run actual baseline before implementation.

After implementation run:

- new tests
- relevant tests
- full suite

Report:

baseline
new tests
modified tests
final total
passed
failed
warnings
regressions

---

# 43. README

Minimal change if new review CLI is added.

Example:

`review-success-style`

Do not change approval count.

Do not claim success_style approved.

---

# 44. PROJECT_STATE

After successful review generation update orientation state.

Expected:

Current Major Stage:
13-4C Human Visual Review

Current Sub-stage:
13-4C-18 Success Style Human Review
Prototype generated / Human decision pending

Canonical:
unchanged

Expected:
12

Approved:
7

Pending:
8

success_style:
PENDING_VISUAL_REVIEW

Human Decision:
NONE

Record:

- review revision/stage
- candidate names
- review artifact path
- next step

Next:

Human opens success_style_review/index.html and chooses candidate.

---

# 45. Git Safety

Do not:

- reset
- clean
- stash
- revert unrelated changes
- delete untracked prompt/history files
- commit
- push

Preserve accumulated work.

Report status only.

---

# 46. External Calls

Expected all 0:

Gemini
YouTube
Video AI
Image AI
Font Network

No external service needed.

---

# 47. WAV / MP4

WAV GENERATED:
NO

MP4 GENERATED:
NO

---

# 48. Human Review Choices

The generated index/report must end with:

SUCCESS STYLE HUMAN REVIEW

1 = <actual candidate 1>
2 = <actual candidate 2>
3 = <actual candidate 3>
4 = 세 후보 모두 부적절 — 새 후보 필요

Do NOT recommend or preselect one in generated artifacts.

Do NOT persist Human approval.

---

# 49. Final Console Output

Expected conceptual output:

SUCCESS STYLE HUMAN REVIEW:
READY

SUCCESS STYLE STATUS:
PENDING_VISUAL_REVIEW

HUMAN DECISION:
NONE

CANONICAL VISUAL CANDIDATE:
CLEAN_DARK_FOCUS

CANONICAL RECORD:
<actual>

SUCCESS SEMANTIC ROLE:
SUCCESS

RESOLVED SUCCESS COLOR:
#4ade80

ACTUAL PLAN 7 SUCCESS USAGE:
<actual investigation result>

FIXED APPROVED CATEGORIES:
- font_family
- background
- color_palette
- typography_scale
- font_weight
- caption_style
- focus_style

SUCCESS STYLE CANDIDATES:

1 = <actual>
    <actual exact properties>

2 = <actual>
    <actual exact properties>

3 = <actual>
    <actual exact properties>

4 = 세 후보 모두 부적절 — 새 후보 필요

APPROVED CATEGORY COUNT:
7

PENDING CATEGORY COUNT:
8

FULL APPROVED VISUAL PROFILE:
NO

READY FOR FINAL RENDERER BINDING:
NO

READY FOR STAGE 13-5:
NO

RENDERER:
NOT_STARTED

REVIEW FIRST:
assets/generated/plan_7/render/success_style_review/index.html

TEST BASELINE:
<actual>

TEST RESULT:
<actual>

EXTERNAL API CALLS:
Gemini 0
YouTube 0
Video AI 0
Image AI 0
Font Network 0

WAV GENERATED:
NO

MP4 GENERATED:
NO

HUMAN DECISION:
NONE

NEXT:
Human reviews Success Style candidates.
Do not persist Success Style approval before the Human decision.
Do not start Stage 13-5.

---

# 50. Completion Report

Return:

## 13-4C-18. Success Style Human Review — 완료 보고

Include:

1. modified/added files
2. architecture
3. source-of-truth investigation
4. actual meaning of success_style
5. actual Plan 7 SUCCESS usage
6. what success_style does not control
7. canonical id before/after
8. visual_design_specs count before/after
9. approved/pending before/after
10. existing 7 approvals preserved
11. success_style before/after
12. Human Decision
13. actual SUCCESS role/value
14. candidate names
15. exact candidate properties
16. evidence/rationale for each candidate
17. proof only success_style varies
18. actual content used
19. contexts generated
20. HTML count
21. side-by-side path
22. index path
23. manifest path
24. accessibility review notes
25. motion separation verification
26. focus separation verification
27. caption separation verification
28. CB06 barrier/timing preservation
29. celebration-content absence
30. approved_visual_profile unchanged
31. previous review artifacts unchanged
32. production_blocks unchanged
33. speech_assets unchanged
34. generated_assets unchanged
35. render_specs unchanged
36. render_timelines unchanged
37. scene_layouts unchanged
38. source_text/display_text unchanged
39. WAV unchanged
40. pronunciation review unchanged
41. validation implementation
42. negative tests
43. determinism
44. browser verification scope
45. Korean/English review scope
46. test baseline
47. new tests
48. modified tests
49. final tests
50. regressions
51. external API counts
52. WAV generated
53. MP4 generated
54. README update
55. PROJECT_STATE update
56. git commit
57. git push
58. bugs
59. semantic debt
60. limitations
61. unresolved critical
62. unresolved non-critical
63. Full Approved Visual Profile
64. Ready for Renderer Binding
65. Ready for Stage 13-5
66. Renderer status
67. Human Review readiness
68. file to open first
69. four Human choices
70. next stage boundary
71. success criteria result

---

# 51. Success Criteria

This stage is successful only if:

- actual project SUCCESS semantics are investigated first
- success_style remains PENDING
- Human Decision remains NONE
- exactly 3 meaningful deterministic candidates exist
- only success_style varies
- SUCCESS palette role is reused
- no new palette color is invented
- existing 7 approved categories remain unchanged
- motion_style remains untouched
- focus_style remains untouched
- caption_style remains untouched
- CB06 timing/barrier/visibility remain unchanged
- no celebration content is invented
- useful review contexts exist
- side-by-side exists
- index exists
- manifest exists
- DB receives zero writes
- canonical id remains unchanged
- approved_visual_profile remains unchanged
- previous review artifacts remain unchanged
- production/audio/layout remain unchanged
- no external API calls occur
- no WAV is generated
- no MP4 is generated
- tests pass
- PROJECT_STATE reflects review-ready state
- Stage 13-5 remains blocked
- Renderer remains NOT_STARTED

If any critical invariant fails:

STOP.

Do not convert this Review stage into an Approval stage.