# Bright Research Instrument GUI Design

## Product Goal

Make the Himawari/GOES desktop tool easier to scan and operate during repeated satellite-image analysis without changing data behavior or established workflows.

## Confirmed Direction

- Visual style: bright research instrument.
- Layout: preserve the current vertical structure and operation order.
- Typography: Segoe UI with a unified text-color hierarchy.
- Motion: lightweight status feedback only.
- Primary action: blue `绘制云图` button.
- Secondary action: neutral `保存图片` button.
- Destructive action: low-emphasis pale-red outlined `清空` button.

## Scope

### Included

- Refine root background, panel surfaces, borders, spacing, label alignment, and control widths.
- Organize the existing vertical controls into three visual groups:
  1. 时间与卫星
  2. 数据类型、波段、色阶与区域
  3. 绘制、保存、清空与进度状态
- Strengthen title hierarchy with tool name, version, and a short purpose line.
- Reduce visual weight around the image display area and preserve maximum cloud-chart space.
- Unify text colors:
  - Primary text: dark charcoal `#243447`.
  - Secondary text: muted blue-gray `#607080`.
  - Disabled text: lighter neutral derived from the same hierarchy.
- Add subtle state feedback:
  - Draw start: button disabled state and status-area reveal.
  - Progress: smooth progressbar value updates and status text changes.
  - Success: brief success-state emphasis, then stable ready state.
  - Error: brief error-state emphasis while retaining explicit error text.
  - Clear: brief image-area fade toward the empty state.

### Excluded

- No change to satellite identifiers, archive windows, time values, provider logic, rendering, downloads, or task invalidation.
- No map-content animation, zoom animation, automatic satellite switching, RGB support, or new controls.
- No dependency on a new UI framework.
- No animation that delays network work or changes worker scheduling.

## Interaction Requirements

- Existing first-use sequence remains: choose date/time and satellite, choose product controls, draw, optionally save or clear.
- All existing readonly selectors remain readonly where currently required.
- Buttons retain text labels that describe outcomes.
- Clear remains easy to understand but visually less prominent than draw.
- Status text remains explicit; color is supplemental and never the only error/success signal.
- Animations must fail harmlessly if the window is closed or a task becomes stale.
- Existing task IDs, stale callback suppression, error dialogs, and progress reset behavior remain unchanged.

## Visual Rules

- Keep vertical rhythm consistent across all parameter rows.
- Align each label and selector to a stable column.
- Use restrained corner radius and borders consistent with Tkinter/ttk capabilities.
- Avoid gradients, decorative blobs, excessive shadows, and large marketing-style elements.
- Keep chart area neutral so satellite imagery remains the dominant visual.
- Ensure disabled controls remain legible and distinguishable.

## Technical Approach

Keep the implementation inside the existing `himawari_gui.py` style setup and UI initialization. Add small style/state helpers only when they reduce repeated styling or state transitions. Use Tkinter `after` callbacks for short visual transitions and cancel or ignore scheduled callbacks when the window/task is stale. Do not alter worker arguments or provider calls.

## Acceptance Criteria

- The GUI opens with the new bright visual hierarchy and no functional regression.
- All existing GUI tests remain green; add focused tests for style configuration and state transitions where feasible without starting Tk.
- Four GOES satellites and Himawari retain their current selection, date-bound, time-slot, and worker behavior.
- Drawing, saving, and clearing remain discoverable and correctly prioritized.
- Progress, success, error, and empty states are visibly distinct and textually explicit.
- No uncaught exceptions occur when a task finishes after a clear action or when the window closes during a transition.
- `py_compile`, static diagnostics, and `git diff --check` pass.
