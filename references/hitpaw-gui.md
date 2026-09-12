# HitPaw Edimakor operational notes

## Control mode: stay in the background

Drive HitPaw with the background app tools so the user's mouse, keyboard focus and frontmost
window are left alone. `request_access` for `HitPaw Edimakor`, then work through
`app_screenshot` / `app_click` / `app_drag` / `app_scroll` with an explicit `window_id`.
These deliver raw input straight into the window; the physical pointer never moves and the app
is never brought to the front.

Confirmed by direct test in background mode: sidebar and tab clicks, the Import button, and
**canvas drags of the selection box**. The removal-mode radios, the Remove button and the 1080P
compatibility dialog are all ordinary controls in the same window and should behave the same way,
but they have not been exercised in background mode yet — check the result rather than assuming.

Background calls on this window come back as "delivered via raw input on AXGroup ... unverified",
because Edimakor exposes no accessibility action to press. That wording means the event was sent,
not that it landed. Always confirm the effect with a fresh `app_screenshot`.

Two coordinate frames exist and they are not the same. `app_screenshot` reports its own frame for
the window; a display-scope `screenshot` reports the monitor's frame. Numbers measured in one are
wrong in the other, so re-measure the preview rectangle after every switch.

## The file-open dialog is the one exception

The macOS open panel is a separate process (`com.apple.appkit.xpc.openAndSavePanelService`).
Background clicks into it are refused, and it cannot be granted: it is not an installed
application, so `request_access` rejects the bundle id outright. `open -a` does not help either,
because Edimakor registers only its own `.hve` project type and will not accept an mp4 as a
document.

This one step cannot avoid disturbing the user, and you should say so before you do it rather than
after. There is a single system-wide keyboard focus: while the panel is up it owns that focus, so
anything the user types lands in the panel's path field alongside your own keystrokes. The mouse
has a background channel, the keyboard does not. Keep the exposure as short as possible:

1. Put the absolute path on the clipboard from the shell with `pbcopy`, saving the previous
   contents with `pbpaste` first and restoring them afterwards. This step sends no keystrokes.
2. `app_click` the Import button in background mode.
3. Tell the user to hold off typing for a couple of seconds.
4. Take full-screen control and send **keyboard actions only**, as one batch: `cmd+shift+g`,
   `cmd+v`, `Return`, `Return`. Four keypresses, about a second. Never `type` the path character
   by character — that stretches the same conflict across roughly eight seconds. Never issue
   clicks, `mouse_move`, or drags while full control is held: those move the user's pointer,
   keyboard actions do not.
5. Call `release_full_control` immediately, before touching anything else, and finish the job in
   background mode.

Never reach the panel with AppleScript, System Events, or shell-driven keystrokes.

## Scope selection

The selected rectangle is expressed in preview coordinates, not source pixels. Determine the visible video bounds from the current screenshot. Convert source coordinates with:

`screen_y = preview_top + source_y / source_height * preview_height`

Use the analogous formula for x. A window resize changes the preview bounds, so measure again.

Resize with the four **mid-edge** handles, one edge at a time. The corner dots move the whole box
instead of resizing it, even when grabbed dead centre, so a corner drag silently costs you the
size you had. Re-measure after every drag: a mid-edge grab that misses by a pixel also translates,
and the box keeping its exact width or height is how you spot it.

Drag an edge outward before you drag the opposite one inward, so the box never has to pass through
an inverted state. To move a band far from where it starts, push the near edge past the target
first, then pull the far edge in.

Use a normal mouse-down/drag/mouse-up gesture rather than assuming fixed coordinates from an earlier session.

## Multiple subtitle positions

One HitPaw task can remove subtitles from several positions in the same video when the selected region covers all of them. Full-frame selection is appropriate for moving or scattered subtitles, but it can also remove legitimate scene text. Always compare full-duration contact sheets before and after.

For multiple input videos, inspect and set the scope per video unless their layout is demonstrably identical. Do not assume that a batch shares one correct rectangle.

## Compatibility conversion

HitPaw may convert a 1080×1920 vertical video to about 608×1080 because it limits the long edge to 1080. This is expected. After removal, upscale to 1080×1920 with Lanczos and mild sharpening. Do not claim the pixels are original resolution; this is a reconstructed delivery resolution.

## Result retrieval

HitPaw logs normally live beneath:

`~/Library/Caches/HitPaw Edimakor/HitpawEdimakor/`

Search the newest log for:

`removeWatermark result url:`

The app may remain on `Downloading...` even after the result exists. The script replaces:

`edimakorpc-us-prod.oss-us-east-1.aliyuncs.com`

with:

`edimakorpc-us-prod.oss-accelerate.aliyuncs.com`

This host is an observed implementation detail and may change. If the accelerated request fails, try the original URL once and inspect current logs instead of resubmitting the AI task.

## Acceptance criteria

- Inspect at least one frame per second for the full duration.
- Inspect scene transitions and the first and last second more densely when needed.
- Confirm no title, instruction subtitle, watermark-like subtitle, or final information card remains.
- Confirm important visual content has not been erased unacceptably.
- Confirm H.264/AAC playback compatibility, expected dimensions and duration, and a full error-free decode.
