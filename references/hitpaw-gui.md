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
4. Take full-screen control, bring Edimakor to the front (`open_application`; if another app such
   as a browser is frontmost the key actions are refused), and send **keyboard actions only**:
   `cmd+shift+g`, wait ~1 s, `cmd+v`, then **zoom on the Go-to field and read the path before any
   `Return`**. The Go-to field is pre-filled with the last directory used, and the paste does not
   always land: on 2026-09-15 the field kept the previous job's `working.mp4`, and the blind
   `Return`, `Return` imported that other video. If the field does not show your path, `cmd+a` and
   `type` the absolute path instead; the extra seconds are cheaper than importing the wrong file.
   Only after the zoom confirms the path, send `Return`, `Return`. Never issue clicks,
   `mouse_move`, or drags while full control is held: those move the user's pointer, keyboard
   actions do not.
5. Call `release_full_control` immediately, before touching anything else, and finish the job in
   background mode. Confirm the imported thumbnail and duration are the intended file. A wrongly
   imported item cannot be removed from the media strip (no exposed delete control, `delete` key
   does nothing); quit Edimakor from its menu and relaunch to get an empty Watermark Remover.

Never reach the panel with AppleScript, System Events, or shell-driven keystrokes.

## Blocking windows and the submit confirmation

- **Home-screen AI Tools tiles crash on background clicks** (Qt segfault in
  `QQuickItem::height()`); click the Watermark Remover tile with a foreground click.
- **Promotional pop-ups** (e.g. a pinned "Fall Special Sale" window shown after launch) are modal:
  every click on the main window is swallowed and the log records nothing. `Escape` does not close
  them. Click only the pop-up's own close `×` in its top-right corner — never a Buy button.
- **The 1080P compatibility dialog** is reported as belonging to another process, so a background
  `app_click` on Confirm can be refused, and a click that looked ineffective can still land late.
  Before clicking Confirm a second time, read the newest log for `WRVRTaskstarted` /
  `addPreDeduction` / `SYVideoRemoveMgrNew taskId`. If any appears after your Remove click, the
  job is already submitted: do not click again.

## Partial resubmission to save credits

Credits scale with duration (about one per second). When only a short stretch still has a caption
— for example a cue missed by an earlier pass — submit a frame-accurate clip of just that stretch
with some margin (`trim=start_frame=A:end_frame=B`, high-quality x264, no audio), then composite the
result back onto the existing cleaned media by frame number, using `overlay` with
`enable='between(n,A,B)'` and the clip timestamps shifted by `A/fps`. Check alignment with the same
offset-PSNR test; the result may again be a couple of frames short, so make sure it still spans the
caption's frames.

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

A HitPaw task takes exactly **one** box, in both Remove watermark and Remove text modes. Dragging
on empty canvas or right-clicking adds no second box. So one task covers several positions only
when a single rectangle spans all of them.

When two positions are far apart, don't widen one box over the space between them (a tall box
repaints everything in between). Handle each position with its own job. Example: a caption band on
every frame plus a title on the first 3 frames. Submit the full video with the band selected. Then
submit a short clip of just the title frames with the title selected. Composite each result only
inside its own mask and frame range (`enable='lte(n,2)'` for the title). The clip must be **at
least 2 seconds** long, or Edimakor rejects it ("only videos of 2 seconds or longer"). A 2.5 s clip
cost 3 credits.

Before drawing, maximize the window by double-clicking its title bar. In the default small window
one screen point covers about eight source pixels.

Full-frame selection is appropriate for moving or scattered subtitles, but it can also remove legitimate scene text. Always compare full-duration contact sheets before and after.

For multiple input videos, inspect and set the scope per video unless their layout is demonstrably identical. Do not assume that a batch shares one correct rectangle.

## Compatibility conversion

HitPaw limits the long edge to 1080, so a vertical 720×1280 or 1080×1920 source is processed and returned at about 608×1080. The "adjust to 1080P" prompt is not optional: the backend downscales whether you confirm or cancel.

Get back to the source resolution before anything else:

- **Band region — composite.** Keep the source as the base and replace only the removal band. Upscale the HitPaw result to the source size, then overlay it through a feathered greyscale band mask; outside the band every pixel is the source's. Check alignment first: HitPaw can drop a frame, so compare PSNR of the result against the source scaled to 608×1080 at offset 0 and offset 1, and use the offset that scores clearly higher. A `-loop 1` mask input needs `-t`, and the command needs `-frames:v <source frame count>`, or the overlay never ends and keeps writing.
- **Full-frame region — upscale.** Scale the whole result to the source size with Lanczos. Say plainly that the delivery pixels are reconstructed, not original resolution.

Then conform to the delivery format with `scripts/conform-vertical.sh RESTORED FINAL`. Every finished file is 1080×1920: fit-scaled, black padding when the aspect is not 9:16, never cropped or stretched, audio copied, every frame kept. A 1080×1920 composite is stream-copied, so it is not re-encoded again.

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

A short job can finish before you start waiting for it. A watcher that only looks for a result
*newer* than when it started will then wait forever. Check the log first: if `removeWatermark result
path:` already names a file under `~/Movies/HitPaw Software/HitPaw Edimakor/AI Generator/WatermrkRemover/`
and `WRVRResultdownloadsucceeded` follows, Edimakor has already downloaded it — copy that local file
instead of waiting or re-downloading.

## Acceptance criteria

- Inspect at least one frame per second for the full duration.
- Inspect scene transitions and the first and last second more densely when needed.
- Confirm no title, instruction subtitle, watermark-like subtitle, or final information card remains.
- Confirm important visual content has not been erased unacceptably.
- Confirm H.264/AAC playback compatibility, exactly 1080×1920 with square pixels, the expected duration, and a full error-free decode. `scripts/verify-clean.sh` fails on any other size.
