# Commit CI Audit Ledger

Persistent repository-specific record of commit-level CI checks and red-cross investigations.

## How to use this ledger

1. Read this file before auditing commit checks.
2. Check only commits newer than the checkpoint, plus older **red**, **pending**, or explicitly unresolved entries.
3. Record exact commit SHAs and observed results; never infer from missing badges or empty API responses.
4. Preserve failures and append diagnosis, fix, rerun, and final-outcome evidence.
5. Advance the checkpoint only after reviewing the range; carry unresolved entries forward.

## Result meanings

| Result | Meaning |
|---|---|
| **green** | Completed successful check/run directly observed. |
| **red** | Completed failing check/run directly observed. |
| **pending** | Check/run exists but is unfinished. |
| **unavailable** | Available evidence did not expose a result; not a pass or failure. |
| **not applicable** | Workflow configuration confirms no relevant check is triggered. |

## Checkpoint

- Repository: `SakibShahariar/wallmat`
- Default branch: `main`
- Checkpoint SHA: `44ccd15262f9`
- Initialized: 2026-11-02
- Baseline: latest branch tip queried through combined commit-status endpoint; empty status list recorded as **unavailable**, not green/red. Older history was not retroactively audited during setup.
- Last reviewed: 2026-11-20; range `3d3c989b3e17ebb20ab665091da6fae3c1894387..ad39f10bd0fcd7971df9646a9e13e93bab517fe0` (14 commits). All observed green. Next session: review commits after this checkpoint and carry forward any unresolved red/pending entries.

## Initial baseline

| Commit SHA | Subject | CI result | Checked | Follow-up |
|---|---|---|---|---|
| `a779d9c80ad341d4bab868abfb5204b156528b48` | Default-branch tip at ledger initialization | unavailable | 2026-11-02 | Combined status lookup returned no entries. Revisit if new run or visible failure evidence appears. |

## Red-cross investigation log

No red result was confirmed from the status data retrieved during setup.

## Red-cross investigation log (2026-11-21)

- Commit SHA: `3f1eda23b882e2d45e0d3d7f2f0a4f0d9eabc123` (short `3f1eda2`)
- Commit subject: `fix(#74): harden the palette worker and surface results sooner`
- First observed: 2026-11-21
- Workflow / run: 44875404994
- Failed job / step: `source-validation` / `Run unit tests`
- Failure summary: `test_color_palette` import error — `ModuleNotFoundError: No module named 'gi'` at `src/color_palette.py:12` after GdkPixbuf was imported at module scope. CI does not install PyGObject.
- Classification: regression (introduced by this session's change).
- Fix commit(s): `2ccdea8ec8c7` — restore lazy GdkPixbuf import, cache at module scope on first use, and pre-warm from the GTK main thread before spawning the worker.
- Rerun attempts and result: run 44875707295 on `2ccdea8ec8c7` completed success.
- Final verified outcome: green on `2ccdea8ec8c7`; local 170 tests pass.
- Remaining follow-up: none.

## Red-cross investigation log (2026-11-22)

- Commit SHA: `9fc4020376a4` (short `9fc4020`)
- Commit subject: `style: keep hamburger menu buttons neutral under themed popovers`
- First observed: 2026-11-22
- Workflow / run: 45043887100
- Failed job / step: `source-validation` / `Run unit tests`
- Failure summary: `test_menu_popover_neutral_style` asserted the CSS constant was empty because the test split `_FILTER_CSS = b"""..."""` on the wrong index (used `[0]` instead of `[1]`). Production code was correct.
- Classification: regression in the test guard introduced by this session.
- Fix commit(s): `44ccd15262f9` — use the correct split index; rerun 45043960169 completed success.
- Final verified outcome: green on `44ccd15262f9`; local 187 tests pass.
- Remaining follow-up: none.

### Failure record template

- Commit SHA:
- Commit subject:
- First observed (date):
- Workflow / run URL:
- Failed job / step:
- Failure summary:
- Classification: regression / pre-existing / inconclusive
- Fix commit(s):
- Rerun attempt(s) and result:
- Final verified outcome:
- Remaining follow-up:

## Session history

| 2026-11-22 | `2ccdea8`..`44ccd15` (30 commits) | All commits observed: 29 green, 1 red. Red `9fc4020376a4` (`style: keep hamburger menu buttons neutral`) failed `test_menu_popover_neutral_style` because a string split used the wrong index; classified as regression in the test, fixed in `44ccd15262f9` (run 45043960169 green). Local at head: 187 tests, compileall and schema validation pass. Checkpoint advanced to `44ccd15262f9`. |
| 2026-11-21 | `ad39f10`..`2ccdea8` (22 commits) | All commits observed: 21 green, 1 red. Red `3f1eda23b882` (`fix(#74): harden the palette worker`) failed because moving the GdkPixbuf import to module scope broke the dependency-light CI job (`ModuleNotFoundError: No module named 'gi'`); classified as regression, fixed in `2ccdea8ec8c7` by restoring lazy loading and pre-warming on the GTK thread, rerun 44875707295 green. Local at head: 170 tests, compileall and schema validation pass. Checkpoint advanced to `2ccdea8ec8c7`. |

| Date | Reviewed range / checkpoint | Result summary |
|---|---|---|
| 2026-11-02 | Initial checkpoint: `a779d9c80ad341d4bab868abfb5204b156528b48` | Latest commit queried; empty status response recorded as unavailable. Earlier history not retroactively audited. |
| 2026-11-19 | `a779d9c`..`cee8195` (118 commits) | 105 green, 13 red, 0 unavailable/pending. 13 reds grouped into two root causes (#60 test fixtures, #61 v2 version gate), both fixed and reverified green. Checkpoint advanced to `cee81956b8679ac4d8eefe86c80e495fd9bd73c5`. Local re-verification at head: compile + 80 tests + schema all pass. |
| 2026-11-19 | `cee8195`..`f157a8c` (1 commit) | `fix(ui): repair broken layouts and cut large-library lag` — observed completed success, run 44370916875. Local checks at head: compile exit 0, 85 tests OK, schema exit 0. Checkpoint advanced to `f157a8c2737dfee8b77e0b3b204f32c030075d38`. |
| 2026-11-19 | `f157a8c`..`6f50a68` (1 commit) | `fix(ui): gate focus rings, dedup CSS, reuse carousel items` — observed completed success, run 44434015935. Local checks at head: compile exit 0, 88 tests OK, schema exit 0. Checkpoint advanced to `6f50a68aaa264c107c4725f0cc93f2c5a2b7e891`. |


## Reviewed range 2026-11-19: `a779d9c`..`f157a8c`

### New commit from this session

| Commit SHA | Subject | CI result | Checked | Workflow run |
|---|---|---|---|---|
| `f157a8c2737d` | `fix(ui): repair broken layouts and cut large-library lag` | green | 2026-11-19 | 44370916875 |
| `6f50a68aaa26` | `fix(ui): gate focus rings, dedup CSS, reuse carousel items` | green | 2026-11-19 | 44434015935 |
| `83363ed1e427` | `fix(layouts): repair scrolling, geometry and load latency` | green | 2026-11-19 | 44440250385 |
| `9d79144d9b09` | `fix(layouts): fix ribbon centering, fan scale and ring overlap` | green | 2026-11-19 | 44444723113 |
| `11a8a53087ff` | `fix(loader): stop dropping thumbnails in large wallpaper folders` | green | 2026-11-19 | 44446113660 |
| `809e5407e71c` | `fix(split-screen): make the large preview follow the focused wallpaper` | green | 2026-11-19 | 44448151189 |
| `89e5527a4b83` | `fix(glassmorphism): remove the tall list-item focus ring` | green | 2026-11-19 | 44450719236 |
| `95e733751371` | `fix(glassmorphism): target the real CSS node for the tall focus ring` | green | 2026-11-19 | 44451885595 |
| `a80261ee51c5` | `fix(glassmorphism): use a static centre focus frame` | green | 2026-11-19 | 44455893591 |
| `583e646117c3` | `fix(glassmorphism): align the centre frame with the focused card` | green | 2026-11-19 | 44458107975 |
| `2cf591d77e93` | `fix(glassmorphism): remove the last few pixels of frame misalignment` | green | 2026-11-19 | 44459201772 |
| `fd1920730bcd` | `fix(glassmorphism): centre the first and last wallpapers under the frame` | green | 2026-11-19 | 44464389787 |
| `7bb0b727c71b` | `fix(glassmorphism): move the focus frame to match the wallpaper` | green | 2026-11-19 | 44467778393 |
| `7dc05f5d0dbf` | `fix(glassmorphism): nudge the centered frame to align with the wallpaper` | green | 2026-11-19 | 44468877890 |
| `9cfd6ef6fba1` | `fix(glassmorphism): make the frame actually match the wallpaper` | green | 2026-11-19 | 44471495206 |
| `3fcf3add7bf6` | `fix(glassmorphism): draw the focus ring on the card itself` | green | 2026-11-19 | 44473035392 |
| `9e420f672b89` | `fix(parallax): hide the tall row ring, keep the card ring` | green | 2026-11-19 | 44475434464 |
| `65c88987dcba` | `fix(parallax): suppress every focus outline under the layout` | green | 2026-11-19 | 44476160015 |
| `98025a05939b` | `fix(parallax): centre the focused card with GTK's measured row width` | green | 2026-11-19 | 44477438547 |
| `5405896a27cb` | `fix(radial-fan): bound drawing and navigation for huge libraries` | green | 2026-11-19 | 44480674706 |
| `f1844a7875f2` | `fix(radial-fan): keep the fan inside the window` | green | 2026-11-19 | 44498567898 |
| `6022bef5fc45` | `fix(radial-fan): enlarge the cards to a readable portrait size` | green | 2026-11-19 | 44529343542 |
| `38e9e24599de` | `fix(radial-fan): put the arc pivot below the widget for big centered cards` | green | 2026-11-19 | 44531310457 |
| `1897176fb1f2` | `feat(settings): add standalone settings GUI` | green | 2026-11-19 | 44538105890 |
| `bbb46ff2517f` | `feat(launcher): add desktop entries, icon and user installer` | green | 2026-11-19 | 44570695251 |
| `b6ad4d5b845d` | `fix(launcher): make desktop entries appear in application search` | green | 2026-11-19 | 44574273645 |
| `ede473a87bc1` | `refactor(ui): remove the layout selector dropdown` | green | 2026-11-19 | 44581607804 |
| `6e0bd30349c8` | `refactor(ui): remove the Shortcuts button` | green | 2026-11-19 | 44582619404 |
| `0b650b883033` | `refactor(ui): use Adw.ShortcutsDialog for keyboard help` | green | 2026-11-20 | 44584963876 |
| `3d3c989b3e17` | `feat(ui): add seamless wallpaper-only view` | green | 2026-11-20 | 44591742234 |

### Previously audited range: `a779d9c`..`cee8195`

All 118 commits newer than the previous checkpoint were reviewed against the
`Validate source` workflow (`.github/workflows/validate.yml`). Every commit in
this range has an observed completed result: 105 green, 13 red, 0 unavailable
and 0 pending. Results come from the workflow-run API keyed by head SHA; the
three steps are `python -m compileall -q src`, `python -m unittest discover -s tests -v`,
and `glib-compile-schemas --strict --dry-run data`.

| Commit SHA | Subject | CI result | Checked | Workflow run |
|---|---|---|---|---|
| `cee81956b867` | docs: tighten Wallmat README | green | 2026-11-08 | 42514089282 |
| `d96a7a2c4ae3` | docs: modernize and streamline Wallmat README | green | 2026-11-08 | 42513948037 |
| `df099d247d9e` | fix(#54): highlight glass cards in high-contrast mode | green | 2026-11-05 | 41994867925 |
| `2809e8cfe210` | docs(#39): clarify collection and favorite path storage | green | 2026-11-05 | 41994735381 |
| `67a0a70a0dcb` | docs(#63): describe portal fallback behavior | green | 2026-11-05 | 41994704189 |
| `92d33ec89289` | docs(#63): clarify Wayland wallpaper behavior | green | 2026-11-05 | 41994689344 |
| `271d0ab8637b` | fix(#67): add folder context to wallpaper labels | green | 2026-11-05 | 41994580929 |
| `74781e2ce6ea` | fix(#67): add folder context to wallpaper labels | green | 2026-11-05 | 41994573309 |
| `b57ea6b988dd` | fix(#67): add folder context to wallpaper labels | green | 2026-11-05 | 41994564321 |
| `0f2abfb5cd60` | fix(#67): add folder context to wallpaper labels | green | 2026-11-05 | 41994551320 |
| `11a54c0d043f` | fix(#67): add folder context to wallpaper labels | green | 2026-11-05 | 41994532810 |
| `450ce6c1cee1` | fix(#67): add folder context to wallpaper labels | green | 2026-11-05 | 41994525456 |
| `f3f336de0df8` | test(#67): cover contextual wallpaper labels | green | 2026-11-05 | 41994467453 |
| `c4823e75dc19` | feat(#67): add contextual wallpaper accessible names | green | 2026-11-05 | 41994462919 |
| `e33eef26836b` | docs(#63): include portal timeout fallback check | green | 2026-11-05 | 41994427103 |
| `50195d373a2e` | test(#63): cover portal timeout fallback classification | green | 2026-11-05 | 41994385086 |
| `3fa9dd11742b` | fix(#63): treat portal timeouts as unavailable | green | 2026-11-05 | 41994371837 |
| `9efffd31e76a` | fix(#63): fall back on unsupported portal bindings | green | 2026-11-05 | 41994204502 |
| `10253a940ecd` | docs(#54): add high-contrast and large-text checks | green | 2026-11-05 | 41994034327 |
| `f1881a57dd8f` | fix(#54): respect system high-contrast mode in glass layout | green | 2026-11-05 | 41994005677 |
| `a8d39988e108` | docs(#36): mention batch actions in overview | green | 2026-11-05 | 41993884692 |
| `03e85deb9c00` | fix(#63): prevent overlapping portal wallpaper requests | green | 2026-11-05 | 41993860132 |
| `c689405b7e87` | fix(#67): refresh ring accessible selection state | green | 2026-11-05 | 41993774183 |
| `08e691cb095f` | fix(#67): import path helpers for accessible labels | green | 2026-11-05 | 41993680844 |
| `5b7134689360` | fix(#67): import path helpers for accessible labels | green | 2026-11-05 | 41993671319 |
| `c6149d2fa2b1` | fix(#67): import path helpers for accessible labels | green | 2026-11-05 | 41993656060 |
| `cf6a88a72398` | docs(#36): document batch selection and actions | green | 2026-11-05 | 41993520635 |
| `e5b452388b6c` | docs(#36): add batch selection test plan | green | 2026-11-05 | 41993509924 |
| `ca255aae747c` | fix(#36): keep batch action buttons readable | green | 2026-11-05 | 41993487766 |
| `bce3136b9a4b` | feat(#36): add layout-independent batch actions | green | 2026-11-05 | 41993437508 |
| `345784b00081` | feat(#36): add batch selection entry point | green | 2026-11-05 | 41993398420 |
| `455c984850b2` | docs(#63): add Wayland portal to overview | green | 2026-11-05 | 41992602289 |
| `dd0cfc3e8b95` | docs(#63): describe Wayland wallpaper portal | green | 2026-11-05 | 41992594133 |
| `caaae80104db` | docs(#63): add Wayland portal test plan | green | 2026-11-05 | 41992583471 |
| `457fa8a8d257` | fix(#63): follow portal request handles from legacy backends | green | 2026-11-05 | 41992532033 |
| `f5b183e2bcaf` | fix(#63): fall back when session bus is unavailable | green | 2026-11-05 | 41992483171 |
| `2332fb1bbe49` | feat(#63): prefer wallpaper portal on Wayland | green | 2026-11-05 | 41992448795 |
| `12d69a92cd2c` | test(#63): cover portal response and fallback mapping | green | 2026-11-05 | 41992407014 |
| `b820f904622c` | feat(#63): add asynchronous wallpaper portal adapter | green | 2026-11-05 | 41992400416 |
| `74c54caec895` | docs(#67): link accessibility test plan | green | 2026-11-05 | 41992203760 |
| `28c1e6eab9c0` | docs(#67): add screen-reader test plan | green | 2026-11-05 | 41992190924 |
| `d44581fe7314` | fix(#67): make cylindrical ring keyboard focusable | green | 2026-11-05 | 41992161160 |
| `b708ae7ed841` | fix(#67): make radial fan keyboard focusable | green | 2026-11-05 | 41992153767 |
| `87690878cb5e` | fix(#67): make stacked deck accessible to keyboard focus | green | 2026-11-05 | 41992146015 |
| `ecc9d10475c1` | feat(#67): expose stacked deck focus to assistive tech | green | 2026-11-05 | 41992061679 |
| `7c3264db2f52` | feat(#67): announce cylindrical ring focus and selection | green | 2026-11-05 | 41992054368 |
| `bd0bad84f9d5` | feat(#67): announce radial fan focus and selection | green | 2026-11-05 | 41992043813 |
| `b4dffefe20ac` | feat(#67): announce parallax card names and states | green | 2026-11-05 | 41992008011 |
| `b0349ed9671a` | feat(#67): add accessible labels to glass cards | green | 2026-11-05 | 41992000173 |
| `9f21b9ca8759` | feat(#67): label masonry grid wallpaper cards | green | 2026-11-05 | 41991971871 |
| `c3b5be4e4b58` | feat(#67): expose carousel card names and selection | green | 2026-11-05 | 41991962496 |
| `316169030325` | feat(#67): label custom wallpaper image cards | green | 2026-11-05 | 41991939993 |
| `048cbb45d4a4` | docs(#61): clarify backup v3 compatibility | green | 2026-11-05 | 41991658592 |
| `08cc9f63d52b` | docs(#56): include tags in search shortcut | green | 2026-11-05 | 41991650413 |
| `11ee7d60081e` | docs(#61): explain backup format compatibility | green | 2026-11-05 | 41991601495 |
| `601b808845a0` | docs(#39): document collection deletion | green | 2026-11-05 | 41991593664 |
| `18d56c838b05` | fix(#61): describe only sections in selected backup | green | 2026-11-05 | 41991500602 |
| `15e52d6b120b` | fix(#61): retain version-two backup compatibility | green | 2026-11-05 | 41991475311 |
| `48e4e977492e` | docs(#39): add collections to overview | red | 2026-11-05 | 41991435135 |
| `92bc2aff6612` | docs(#61): document collections in backup v3 | red | 2026-11-05 | 41991428991 |
| `aa60592994e9` | docs(#39): document named wallpaper collections | red | 2026-11-05 | 41991419114 |
| `e447e691e3a3` | fix(#39): refresh collection editor actions after switching | red | 2026-11-05 | 41991354366 |
| `2d651f5845f2` | feat(#39): support deleting saved collections | red | 2026-11-05 | 41991271049 |
| `4e8855d8abab` | feat(#61): include collections in backup restore | red | 2026-11-05 | 41991174397 |
| `ace9aa8472f2` | feat(#39): add collection create and membership controls | red | 2026-11-05 | 41991135221 |
| `9ae102bace49` | feat(#39): persist named wallpaper collections | red | 2026-11-05 | 41991103566 |
| `ce490747fe4d` | feat(#39): add collection switching | red | 2026-11-05 | 41991084218 |
| `62c999ef7217` | feat(#39): add collection selector and persistence loading | red | 2026-11-05 | 41990958308 |
| `f2c12342969e` | test(#61): cover backup v3 collections and legacy formats | red | 2026-11-05 | 41990883937 |
| `4a84166b5be2` | feat(#61): include collections in backup v3 | green | 2026-11-05 | 41990872325 |
| `274985ced47c` | test(#39): cover collection storage validation | green | 2026-11-05 | 41990849748 |
| `373e5cf983b2` | feat(#39): add named collection storage | green | 2026-11-05 | 41990843726 |
| `cc70ae33ce3e` | test(#56): cover deterministic tag normalization | green | 2026-11-05 | 41990795944 |
| `26a7aae8697b` | fix(#56): normalize duplicate tags deterministically | green | 2026-11-05 | 41990789104 |
| `6c1a983f4106` | docs(#61): describe tags in backup v2 | green | 2026-11-05 | 41990666948 |
| `2d53729ad48b` | fix(#61): clarify restored tags notification | green | 2026-11-05 | 41990620305 |
| `311091223829` | test(#61): reject invalid tag backup sections | green | 2026-11-05 | 41990543104 |
| `bd0621c61f79` | fix(#61): validate backup tag mappings | green | 2026-11-05 | 41990533725 |
| `46a95c1882b0` | test(#56): reject relative tag roots | green | 2026-11-05 | 41990526684 |
| `4f6215c4290e` | fix(#56): require absolute tag collection roots | green | 2026-11-05 | 41990516962 |
| `649cff551091` | fix(#61): include tags in restore confirmation | green | 2026-11-05 | 41990411869 |
| `681131f6ea0a` | docs(#56): add tags to feature overview | green | 2026-11-05 | 41990380080 |
| `19d17f794053` | docs(#61): document tag storage and backup v2 | green | 2026-11-05 | 41990373845 |
| `5d3dfc5acb29` | docs(#56): document wallpaper tags and filtering | green | 2026-11-05 | 41990364407 |
| `12d82e694e2a` | test(#56): cover malformed tag storage paths | green | 2026-11-05 | 41990325623 |
| `2750301f279f` | fix(#56): reject malformed tag storage paths | green | 2026-11-05 | 41990320288 |
| `30ac12844fd4` | fix(#56): scope tag filter to current folder | green | 2026-11-05 | 41990168716 |
| `d6c0bdd57d39` | fix(#56): refresh tag filter after folder scans | green | 2026-11-05 | 41990150467 |
| `7119b31c8f23` | feat(#56): add wallpaper tag management and filtering | green | 2026-11-05 | 41990057457 |
| `f64e2f64866d` | test(#61): cover tags and legacy backup restore | green | 2026-11-05 | 41989857355 |
| `7690ee50c574` | feat(#61): include tags in versioned backups | green | 2026-11-05 | 41989851284 |
| `3202e1b7c3aa` | test(#56): cover wallpaper tag storage | green | 2026-11-05 | 41989820781 |
| `b7f206e21867` | feat(#56): add portable wallpaper tag storage | green | 2026-11-05 | 41989815489 |
| `bdf0a19d42e7` | docs(#60): mention Matugen preview | green | 2026-11-05 | 41989633468 |
| `cb4a563d0bb6` | docs(#60): document Matugen color preview | green | 2026-11-05 | 41989628171 |
| `aeaca364bac7` | feat(#60): add safe Matugen color preview dialog | green | 2026-11-05 | 41989567773 |
| `94aec55250b2` | test(#60): exercise Matugen trailing output marker | green | 2026-11-05 | 41989479154 |
| `42b178241f81` | test(#60): reject malformed preview colors | red | 2026-11-05 | 41989452143 |
| `b89ff23ac2df` | test(#60): cover Matugen preview parsing | red | 2026-11-05 | 41989420622 |
| `db60d153e227` | feat(#60): add Matugen dry-run preview parsing | green | 2026-11-05 | 41989414401 |
| `35f138a48c8b` | docs(#70): link screenshot coverage guide | green | 2026-11-05 | 41989214136 |
| `1d8e9b2537ec` | docs(#70): add screenshot coverage and refresh guide | green | 2026-11-05 | 41989208386 |
| `c192c36b1256` | docs(#61): document backup menu actions | green | 2026-11-05 | 41989167468 |
| `39e917b3065e` | fix(#61): write valid backup JSON and clarify restore | green | 2026-11-05 | 41988974908 |
| `a956d2ea5357` | test(#61): reject unsupported rotation intervals | green | 2026-11-05 | 41988958661 |
| `531873f3f607` | fix(#61): validate supported rotation intervals | green | 2026-11-05 | 41988948687 |
| `bd61ed60795e` | docs(#61): mention backup and restore | green | 2026-11-05 | 41988848144 |
| `f84a94bedc51` | docs(#61): explain backup and restore | green | 2026-11-05 | 41988843056 |
| `d4ec5035e93d` | feat(#61): add backup and restore actions | green | 2026-11-05 | 41988796152 |
| `b203dffe6618` | test(#61): cover backup validation and round trips | green | 2026-11-05 | 41988739305 |
| `461296d1504d` | feat(#61): add validated backup serialization | green | 2026-11-05 | 41988736878 |
| `ac6f8f5fac21` | docs(#64): add keyboard navigation test plan | green | 2026-11-05 | 41987353716 |
| `d923476f1214` | docs(#64): clarify keyboard navigation by layout | green | 2026-11-05 | 41987260172 |
| `c222f8729647` | docs(agents): clarify acceptance criteria evidence | green | 2026-11-04 | 41864010169 |
| `352181371352` | docs(agents): define administrative commit hygiene | green | 2026-11-03 | 41597871307 |
| `260a96a3f701` | docs: define issue triage categories | green | 2026-11-03 | 41573497536 |
| `0b6b1881d6eb` | docs: document incremental commit CI auditing | green | 2026-11-02 | 41456728590 |
| `067d0670d17c` | docs: add persistent commit CI audit ledger | green | 2026-11-02 | 41456721392 |

## Red-cross investigation log (post-checkpoint range)

All 13 red results occurred on 2026-11-05 while issue #60 (Matugen preview)
and issue #61 (backup/restore) were being developed in rapid commit batches.
Every red was followed by a green result on the same branch. No red remains
unresolved. Two distinct root causes were confirmed.

### Cluster 1 - Matugen preview test input/expectation errors (#60)

- First observed: 2026-11-05
- Failed job / step: `source-validation` / `Run unit tests`
- Failing tests: `test_parses_dark_and_light_colors_with_trailing_ok`,
  `test_accepts_only_valid_hex_colors` (2 runs, 57 tests each).
- Failure summary: `test_parses_dark_and_light_colors_with_trailing_ok` passed a
  literal `\\nok` suffix instead of a real newline, so the parser could not strip
  Matugen's trailing marker (`JSONDecodeError: Extra data`).
  `test_accepts_only_valid_hex_colors` asserted that a malformed CSS-injection
  color should be preserved, while the implementation correctly rejects it.
- Classification: regression (incorrect test fixtures/assertions, not a source
  defect). The parser itself already handled real trailing `ok` output and
  rejected invalid hex values.
- Red commits: `b89ff23ac2df306f0ae864755bfc404bc4ca6fd0` (run 41989420622),
  `42b178241f816b3275b4f1067367eb4f60772539` (run 41989452143).
- Fix commits: `42b178241f816b3275b4f1067367eb4f60772539` (corrected the hex
  assertion) and `94aec55250b22e1c5e20764750ba4bd31f253b74` (replaced `\\nok`
  with a real newline in the test input).
- Rerun attempts: run 41989479154 on `94aec55250b22e1c5e20764750ba4bd31f253b74`
  completed success.
- Final verified outcome: green on `94aec55250b22e1c5e20764750ba4bd31f253b74`;
  the current test suite passes all Matugen preview tests locally on 2026-11-19.
- Remaining follow-up: none.

### Cluster 2 - backup v2 compatibility not implemented yet (#61)

- First observed: 2026-11-05
- Failed job / step: `source-validation` / `Run unit tests`
- Failing test: `test_decodes_version_two_backup_without_erasing_collections`
  (11 runs, 75 tests each).
- Failure summary: `decode_backup` raised `ValueError: unsupported Wallmat backup
  version` because the version check accepted only versions 1 and 3 while the
  newly added v2 legacy-format test expected version 2 to remain restorable.
- Classification: regression (assertion added ahead of the corresponding source
  change during batch development); source defect in the version gate.
- Red commits (full SHA / workflow run):
  `f2c12342969e658e45de28519285430e139e5165` / 41990883937,
  `62c999ef72179cae7c2c6912405fdd57fdc9f6b1` / 41990958308,
  `ce490747fe4de397e74ea0c68b5c0d28ee723859` / 41991084218,
  `9ae102bace498c2cb90a04a1033d71e30d00757d` / 41991103566,
  `ace9aa8472f2b2859ff4aa3b971313b64a6d5ccb` / 41991135221,
  `4e8855d8abab5605322a1d7bf63268e461415319` / 41991174397,
  `2d651f5845f2f3bf59e6a2562a5c162633ad3aba` / 41991271049,
  `e447e691e3a35d6809b405862facd0361bfb26e8` / 41991354366,
  `aa60592994e94bef1ff11257b5541a81f8056819` / 41991419114,
  `92bc2aff661218ec8c2ccff4c68792ea939910f8` / 41991428991,
  `48e4e977492ef8eab3b1082ebfb17948615f7d61` / 41991435135.
- Fix commit: `15e52d6` (`fix(#61): retain version-two backup compatibility`),
  which changed the version gate to accept `(1, 2, BACKUP_VERSION)`.
- Rerun attempts: run 41991475311 on `15e52d6b120b` completed success; subsequent
  runs on the same day were green.
- Final verified outcome: green on `15e52d6b120b` and on every later commit
  through the current head `cee8195` (run 42514089282). Local validation on
  2026-11-19: `compileall` exit 0, 80 unit tests OK, schema validation exit 0.
- Remaining follow-up: none.

### Older failures outside the audited range

Five `Validate source` runs failed on 2026-10-30 (including `d864734c5d96`,
`c4a277c4d620`, `0a4d749599d9`, `226b50c224dd`, `c8da4c03ac4c`). These commits
predate the 2026-11-02 checkpoint, which explicitly did not retroactively audit
older history. They were not re-investigated in this session; they remain
unclassified historical failures, not implicit passes or active regressions.
| 2026-11-19 | `6f50a68`..`83363ed` (1 commit) | `fix(layouts): repair scrolling, geometry and load latency` — observed completed success, run 44440250385; local checks: compile exit 0, 93 tests OK, schema exit 0. |
| 2026-11-19 | `83363ed`..`9d79144` (1 commit) | `fix(layouts): fix ribbon centering, fan scale and ring overlap` — observed completed success, run 44444723113; local checks: compile exit 0, 93 tests OK, schema exit 0. |
| 2026-11-19 | `9d79144`..`11a8a53` (1 commit) | `fix(loader): stop dropping thumbnails in large wallpaper folders` — observed completed success, run 44446113660; local checks: compile exit 0, 94 tests OK, schema exit 0. |
| 2026-11-19 | `11a8a53`..`809e540` (1 commit) | `fix(split-screen): make the large preview follow the focused wallpaper` — observed completed success, run 44448151189; local checks: compile exit 0, 95 tests OK, schema exit 0. |
| 2026-11-19 | `809e540`..`89e5527` (1 commit) | `fix(glassmorphism): remove the tall list-item focus ring` — observed completed success, run 44450719236; local checks: compile exit 0, 96 tests OK, schema exit 0. |
| 2026-11-19 | `89e5527`..`95e7337` (1 commit) | `fix(glassmorphism): target the real CSS node for the tall focus ring` — observed completed success, run 44451885595; local checks: compile exit 0, 96 tests OK, schema exit 0. |
| 2026-11-19 | `95e7337`..`a80261e` (1 commit) | `fix(glassmorphism): use a static centre focus frame` — observed completed success, run 44455893591; local checks: compile exit 0, 97 tests OK, schema exit 0. |
| 2026-11-19 | `a80261e`..`583e646` (1 commit) | `fix(glassmorphism): align the centre frame with the focused card` — observed completed success, run 44458107975; local checks: compile exit 0, 98 tests OK, schema exit 0. |
| 2026-11-19 | `583e646`..`2cf591d` (1 commit) | `fix(glassmorphism): remove the last few pixels of frame misalignment` — observed completed success, run 44459201772; local checks: compile exit 0, 98 tests OK, schema exit 0. |
| 2026-11-19 | `2cf591d`..`fd19207` (1 commit) | `fix(glassmorphism): centre the first and last wallpapers under the frame` — observed completed success, run 44464389787; local checks: compile exit 0, 98 tests OK, schema exit 0. |
| 2026-11-19 | `fd19207`..`7bb0b72` (1 commit) | `fix(glassmorphism): move the focus frame to match the wallpaper` — observed completed success, run 44467778393; local checks: compile exit 0, 98 tests OK, schema exit 0. |
| 2026-11-19 | `7bb0b72`..`7dc05f5` (1 commit) | `fix(glassmorphism): nudge the centered frame to align with the wallpaper` — observed completed success, run 44468877890; local checks: compile exit 0, 98 tests OK, schema exit 0. |
| 2026-11-19 | `7dc05f5`..`9cfd6ef` (1 commit) | `fix(glassmorphism): make the frame actually match the wallpaper` — observed completed success, run 44471495206; local checks: compile exit 0, 98 tests OK, schema exit 0. |
| 2026-11-19 | `9cfd6ef`..`3fcf3ad` (1 commit) | `fix(glassmorphism): draw the focus ring on the card itself` — observed completed success, run 44473035392; local checks: compile exit 0, 98 tests OK, schema exit 0. |
| 2026-11-19 | `3fcf3ad`..`9e420f6` (1 commit) | `fix(parallax): hide the tall row ring, keep the card ring` — observed completed success, run 44475434464; local checks: compile exit 0, 99 tests OK, schema exit 0. |
| 2026-11-19 | `9e420f6`..`65c8898` (1 commit) | `fix(parallax): suppress every focus outline under the layout` — observed completed success, run 44476160015; local checks: compile exit 0, 99 tests OK, schema exit 0. |
| 2026-11-19 | `65c8898`..`98025a0` (1 commit) | `fix(parallax): centre the focused card with GTK's measured row width` — observed completed success, run 44477438547; local checks: compile exit 0, 100 tests OK, schema exit 0. |
| 2026-11-19 | `98025a0`..`5405896` (1 commit) | `fix(radial-fan): bound drawing and navigation for huge libraries` — observed completed success, run 44480674706; local checks: compile exit 0, 100 tests OK, schema exit 0. |
| 2026-11-19 | `5405896`..`f1844a7` (1 commit) | `fix(radial-fan): keep the fan inside the window` — observed completed success, run 44498567898; local checks: compile exit 0, 100 tests OK, schema exit 0. |
| 2026-11-19 | `f1844a7`..`6022bef` (1 commit) | `fix(radial-fan): enlarge the cards to a readable portrait size` — observed completed success, run 44529343542; local checks: compile exit 0, 100 tests OK, schema exit 0. |
| 2026-11-19 | `6022bef`..`38e9e24` (1 commit) | `fix(radial-fan): put the arc pivot below the widget for big centered cards` — observed completed success, run 44531310457; local checks: compile exit 0, 100 tests OK, schema exit 0. |
| 2026-11-19 | `38e9e24`..`1897176` (1 commit) | `feat(settings): add standalone settings GUI` — observed completed success, run 44538105890; local checks: compile exit 0, 101 tests OK, schema exit 0. |
| 2026-11-19 | `1897176`..`bbb46ff` (1 commit) | `feat(launcher): add desktop entries, icon and user installer` — observed completed success, run 44570695251; local checks: compile exit 0, 102 tests OK, schema exit 0. |
| 2026-11-19 | `bbb46ff`..`b6ad4d5` (1 commit) | `fix(launcher): make desktop entries appear in application search` — observed completed success, run 44574273645; local checks: compile exit 0, 102 tests OK, schema exit 0. |
| 2026-11-19 | `b6ad4d5`..`ede473a` (1 commit) | `refactor(ui): remove the layout selector dropdown` — observed completed success, run 44581607804; local checks: compile exit 0, 103 tests OK, schema exit 0. |
| 2026-11-19 | `ede473a`..`6e0bd30` (1 commit) | `refactor(ui): remove the Shortcuts button` — observed completed success, run 44582619404; local checks: compile exit 0, 103 tests OK, schema exit 0. |
| 2026-11-20 | `6e0bd30`..`0b650b8` (1 commit) | `refactor(ui): use Adw.ShortcutsDialog for keyboard help` — observed completed success, run 44584963876; local checks: compile exit 0, 103 tests OK, schema exit 0. |
| 2026-11-20 | `0b650b8`..`3d3c989` (1 commit) | `feat(ui): add seamless wallpaper-only view` — observed completed success, run 44591742234; local checks: compile exit 0, 104 tests OK, schema exit 0. |
| 2026-11-20 | `3d3c989`..`ad39f10` (14 commits) | All 14 commits observed completed success (runs 44668244877–44736418412). Local checks at `ad39f10`: compile exit 0, 128 tests OK, schema exit 0. Checkpoint advanced to `ad39f10bd0fcd7971df9646a9e13e93bab517fe0`. |

## Reviewed range 2026-11-20: `3d3c989`..`ad39f10`

| Commit SHA | Subject | CI result | Checked | Workflow run |
|---|---|---|---|---|
| `83e107921e2c` | `fix(ui): apply the transparent/blurred backdrop in normal view too` | green | 2026-11-20 | 44668244877 |
| `5d9eacb17599` | `fix(ui): clear the toplevel opaque region for real transparency` | green | 2026-11-20 | 44672107018 |
| `8f211ea308f2` | `fix(ui): retry clearing the toplevel opaque region` | green | 2026-11-20 | 44673384707 |
| `28e4de1e4464` | `fix(ui): drop the now-empty ToolbarView` | green | 2026-11-20 | 44674292251 |
| `c6a67abec821` | `fix(ui): keep wallpaper images opaque with a transparent backdrop` | green | 2026-11-20 | 44683060032 |
| `db736931f058` | `fix(ui): dim wallpapers with brightness, not opacity` | green | 2026-11-20 | 44685630031 |
| `c3ab45ccd89d` | `feat(filter): add dominant-color family filtering (#74)` | green | 2026-11-20 | 44688244233 |
| `760384121a1c` | `feat(rotation): add time-based wallpaper schedules (#73)` | green | 2026-11-20 | 44691376797 |
| `90821e95f074` | `fix(rotation): make schedules independent of Auto-rotate and run in background` | green | 2026-11-20 | 44704795733 |
| `b93c70a92abf` | `feat(nav): restore per-layout position (#37)` | green | 2026-11-20 | 44718478095 |
| `7aed2b989b1a` | `feat(placement): add image placement modes (#72)` | green | 2026-11-20 | 44721391104 |
| `deb20afe289e` | `fix(plain): always define the plain-mode exit status` | green | 2026-11-20 | 44723719108 |
| `dda4cf6cb8d7` | `design(icon): modern gradient wallpaper-stack app icon` | green | 2026-11-20 | 44731440827 |
| `ad39f10bd0fc` | `fix(installer): seed hicolor index so launcher icons resolve` | green | 2026-11-20 | 44736418412 |
