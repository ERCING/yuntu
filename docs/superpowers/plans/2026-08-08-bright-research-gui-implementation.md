# Bright Research Instrument GUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Polish the existing Tkinter GUI into a bright research-instrument interface with unified typography, clearer vertical grouping, and safe lightweight state feedback.

**Architecture:** Keep all UI work inside `himawari_gui.py` and its existing style system. Add small state-style helpers only for visual transitions; worker arguments, provider calls, task IDs, date/time controls, and error semantics remain unchanged. Test visual configuration and state transitions through the existing fake GUI fixtures without starting Tk.

**Tech Stack:** Python 3.13, Tkinter/ttk, Matplotlib Tk canvas, unittest.

---

## Files

- Modify: `himawari_ir_toolkit/himawari_gui.py` — styles, layout grouping, labels, progress/status transitions, lightweight `after` feedback.
- Modify: `himawari_ir_toolkit/tests/test_gui_threading.py` — static/style/state tests using existing fakes.

## Task 1: Lock the Visual System

**Files:**
- Modify: `himawari_ir_toolkit/himawari_gui.py`
- Test: `himawari_ir_toolkit/tests/test_gui_threading.py`

- [ ] **Step 1: Add failing static style tests**

```python
def test_bright_research_palette_is_defined(self):
    source = Path(HIMAWARI_GUI).read_text(encoding="utf-8")
    self.assertIn("#243447", source)
    self.assertIn("#607080", source)
    self.assertIn("#1769AA", source)
    self.assertIn("Segoe UI", source)
    self.assertNotIn("#000000", source)


def test_primary_secondary_and_danger_styles_have_distinct_roles(self):
    source = Path(HIMAWARI_GUI).read_text(encoding="utf-8")
    self.assertIn("Primary.TButton", source)
    self.assertIn("Secondary.TButton", source)
    self.assertIn("Danger.TButton", source)
    self.assertIn("#1769AA", source)
    self.assertIn("#FDECEC", source)
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m unittest himawari_ir_toolkit.tests.test_gui_threading.TestBrightResearchStyles -v
```

Expected: failures because the current style source uses the old palette and black text.

- [ ] **Step 3: Implement the palette and consistent styles**

Use these constants in `_setup_styles`:

```python
bg_color = '#FFFFFF'
panel_bg = '#F4F7FA'
card_bg = '#FFFFFF'
border_color = '#D6E0E8'
text_color = '#243447'
muted_text = '#607080'
primary_color = '#1769AA'
hover_color = '#145A91'
danger_bg = '#FDECEC'
danger_border = '#D77A7A'
```

Apply `text_color` to all primary labels, titles, combobox foregrounds, and buttons. Apply `muted_text` to subtitles, units, and progress support text. Keep the chart figure background white. Configure `Danger.TButton` with pale red background/border and dark red text, not a filled red block.

- [ ] **Step 4: Run style tests and static checks**

```powershell
python -m unittest himawari_ir_toolkit.tests.test_gui_threading.TestBrightResearchStyles -v
python -m py_compile himawari_ir_toolkit/himawari_gui.py
```

Expected: all style tests pass and compilation succeeds.

- [ ] **Step 5: Commit**

```powershell
git add himawari_ir_toolkit/himawari_gui.py himawari_ir_toolkit/tests/test_gui_threading.py
git commit -m "style: establish bright research GUI palette"
```

## Task 2: Improve Vertical Hierarchy and Copy

**Files:**
- Modify: `himawari_ir_toolkit/himawari_gui.py`
- Test: `himawari_ir_toolkit/tests/test_gui_threading.py`

- [ ] **Step 1: Add failing copy/layout tests**

```python
def test_gui_uses_research_instrument_section_labels(self):
    source = Path(HIMAWARI_GUI).read_text(encoding="utf-8")
    self.assertIn("时间与卫星", source)
    self.assertIn("数据与显示", source)
    self.assertIn("绘制与输出", source)
    self.assertIn("卫星云图分析工具", source)


def test_existing_user_actions_remain_present(self):
    source = Path(HIMAWARI_GUI).read_text(encoding="utf-8")
    for label in ("绘制云图", "保存图片", "清空", "日期时间 (UTC)"):
        self.assertIn(label, source)
```

- [ ] **Step 2: Run tests and verify they fail**

```powershell
python -m unittest himawari_ir_toolkit.tests.test_gui_threading.TestBrightResearchCopy -v
```

Expected: failures because the current UI has only `参数设置` and `云图显示` labels.

- [ ] **Step 3: Implement visual grouping without changing control ownership**

Keep the same vertical pack order, but rename the control LabelFrame and add three small section labels or nested frames:

```python
ttk.Label(control_frame, text="时间与卫星", style='Section.TLabel').pack(anchor='w', pady=(0, 6))
# existing date and platform frames

ttk.Label(control_frame, text="数据与显示", style='Section.TLabel').pack(anchor='w', pady=(8, 6))
# existing data type, band, scheme, region frames

ttk.Label(control_frame, text="绘制与输出", style='Section.TLabel').pack(anchor='w', pady=(8, 6))
# existing buttons and progress widgets
```

Update the title to `Himawari / GOES 卫星云图分析工具`; keep version text and add a short subtitle `UTC 数据选择 · 全圆盘云图绘制`. Configure `Section.TLabel` with the same unified text color and a compact semibold font. Do not rename button commands, variables, platform values, or data labels.

- [ ] **Step 4: Run copy/layout tests and regression**

```powershell
python -m unittest himawari_ir_toolkit.tests.test_gui_threading.TestBrightResearchCopy -v
python -m unittest discover -s himawari_ir_toolkit/tests -t . -v
```

Expected: copy tests pass and all existing tests remain green.

- [ ] **Step 5: Commit**

```powershell
git add himawari_ir_toolkit/himawari_gui.py himawari_ir_toolkit/tests/test_gui_threading.py
git commit -m "style: clarify GUI control hierarchy"
```

## Task 3: Add Safe Lightweight State Feedback

**Files:**
- Modify: `himawari_ir_toolkit/himawari_gui.py`
- Test: `himawari_ir_toolkit/tests/test_gui_threading.py`

- [ ] **Step 1: Add failing state-transition tests**

```python
def test_state_feedback_helpers_use_cancelable_after_callbacks(self):
    source = Path(HIMAWARI_GUI).read_text(encoding="utf-8")
    self.assertIn("_show_status_feedback", source)
    self.assertIn("after", source)
    self.assertIn("after_cancel", source)


def test_clear_state_keeps_task_invalidation_before_visual_feedback(self):
    source = Path(HIMAWARI_GUI).read_text(encoding="utf-8")
    clear_pos = source.index("def _clear_image")
    task_reset_pos = source.index("self._active_task_id = None", clear_pos)
    feedback_pos = source.find("_show_status_feedback", clear_pos)
    self.assertTrue(feedback_pos == -1 or task_reset_pos < feedback_pos)
```

- [ ] **Step 2: Run tests and verify they fail**

```powershell
python -m unittest himawari_ir_toolkit.tests.test_gui_threading.TestBrightResearchMotion -v
```

Expected: failures because no cancelable visual feedback helper exists.

- [ ] **Step 3: Implement minimal cancelable feedback**

Add a helper that only changes visual state and text:

```python
def _show_status_feedback(self, kind, message, duration=900):
    if getattr(self, '_status_feedback_after_id', None) is not None:
        try:
            self.root.after_cancel(self._status_feedback_after_id)
        except tk.TclError:
            pass
        self._status_feedback_after_id = None
    self.progress_var.set(message)
    self.progress_label.configure(style=f'{kind}.Progress.TLabel')
    try:
        self._status_feedback_after_id = self.root.after(
            duration, lambda: self.progress_label.configure(style='Progress.TLabel')
        )
    except tk.TclError:
        self._status_feedback_after_id = None
```

Use it only at existing UI-thread state points:

- `_draw_image`: `Working.Progress.TLabel`, message `正在准备绘制...`.
- Successful result callback: `Success.Progress.TLabel`, existing success message.
- Error callback: `Error.Progress.TLabel`, existing explicit error message.
- `_clear_image`: `Progress.TLabel`, existing `就绪` message after task invalidation and resource cleanup.

Use `after` only for the short visual reset; never schedule network or worker operations. Keep stale callback guards before any feedback call.

- [ ] **Step 4: Run motion tests and full regression**

```powershell
python -m unittest himawari_ir_toolkit.tests.test_gui_threading.TestBrightResearchMotion -v
python -m unittest discover -s himawari_ir_toolkit/tests -t . -v
python -m py_compile himawari_ir_toolkit/himawari_gui.py
```

Expected: state tests pass, full regression remains green, compilation succeeds.

- [ ] **Step 5: Commit**

```powershell
git add himawari_ir_toolkit/himawari_gui.py himawari_ir_toolkit/tests/test_gui_threading.py
git commit -m "style: add lightweight GUI state feedback"
```

## Task 4: Product Acceptance and Visual Smoke Check

**Files:**
- Modify only if a concrete acceptance failure requires it: `himawari_gui.py` or the focused GUI test file.

- [ ] **Step 1: Run complete local verification**

```powershell
python -m unittest discover -s himawari_ir_toolkit/tests -t . -v
git diff --check
python -m py_compile himawari_ir_toolkit/himawari_gui.py
```

Expected: all tests pass, no whitespace errors, and no diagnostics.

- [ ] **Step 2: Launch through the supported environment entrypoint**

```powershell
& ".\start_gui.bat"
```

Check manually:

- Title, subtitle, section labels, and all text use the unified color hierarchy.
- Date/time and satellite controls remain usable, including all 144 GOES ten-minute slots.
- Draw is visually primary, save is neutral, clear is low-emphasis red outline.
- Progress, success, error, and empty states are distinguishable without relying only on color.
- Existing GOES-16/17/18/19 archive clamping and Himawari behavior remain unchanged.

- [ ] **Step 3: Run focused regression after manual smoke check**

```powershell
python -m unittest discover -s himawari_ir_toolkit/tests -t . -v
```

Expected: same green result after the GUI is closed.

- [ ] **Step 4: Commit concrete acceptance fixes only**

```powershell
git status --short
git diff --check
```

Do not add build/release output or generated files.

## Self-Review

- Palette, typography, grouping, copy, and state feedback from the spec are covered by Tasks 1–3.
- Data behavior, satellite selection, date bounds, time values, worker args, and task invalidation are explicitly preserved and regression-tested in every task.
- UI motion is limited to cancelable status styling and does not affect worker scheduling or downloads.
- No new framework, network dependency, or generated build output is introduced.
- All commands use the repository's actual test discovery path `himawari_ir_toolkit/tests`.
