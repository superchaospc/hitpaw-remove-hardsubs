# HitPaw Remove Hardsubs

一个给 Claude Code 和 Codex 用的 skill：驱动 macOS 上的 HitPaw Edimakor，把视频里烧死的硬字幕去掉，然后验收成品。

它解决的不是"怎么点 HitPaw"，而是三件人容易做错的事：**字幕到底在哪一行**、**任务跑完了结果在哪**、**擦干净了没有**。这三件每一件做错都要再花一次付费额度。

## 它做什么

- 用逐行边缘检测在**整幅画面高度**上定位字幕，输出每一帧的行区间，而不是靠肉眼看缩略图。
- 把全片检出的行区间取并集，给出擦除带；或者在字幕位置太散时建议整帧擦除，并说明会损伤什么。
- 以**后台模式**驱动 HitPaw，你的鼠标和当前窗口不受影响。只有系统文件对话框那一两秒需要键盘。
- 任务完成后从 HitPaw 的本地日志里取回结果，包括 App 自己下载失败、卡片显示 "Failed to download" 的情况。
- 对成品跑同一套检测，用"每一帧都没有检出"来证明覆盖完整，而不是抽查几张缩略图。
- **成品统一是竖屏 1080×1920**，不管原片是 720×1280、1080×1920 还是横屏。先恢复到原片分辨率保住细节，再等比转成 1080×1920（比例不是 9:16 时补黑边，不裁切不拉伸），验收脚本不是这个尺寸就判失败。

## 前置条件

- macOS，已安装并登录 **HitPaw Edimakor**。这是付费工具，每个任务消耗 AI 额度，本 skill 不会替你购买。
- `ffmpeg` / `ffprobe`。
- Python 3 与 `numpy`（字幕行扫描和合成脚本要用）。macOS 自带或 Homebrew 的最新版 Python 常常没装 numpy，也装不上（例如 3.14），那就用一个装了 numpy 的 venv 里的 python 来跑脚本。
- Claude Code 或 Codex，且具备桌面控制能力。没有的话 skill 会准备好素材和清单后停下，不会谎称已提交。

## 安装

```bash
git clone https://github.com/superchaospc/hitpaw-remove-hardsubs.git \
  ~/.claude/skills/hitpaw-remove-hardsubs
```

要让 Codex 也能自动触发，软链过去即可，两边是同一种 skill 格式：

```bash
ln -s ~/.claude/skills/hitpaw-remove-hardsubs ~/.codex/skills/hitpaw-remove-hardsubs
```

## 使用

直接说人话就行，skill 会自己触发：

- 「自动去掉这个视频的全部字幕。」
- 「字幕在多个地方出现，帮我全画面去字并验收。」
- 「HitPaw 已处理完成但一直卡在 Downloading，帮我取回。」
- 「把 Downloads 里的三条视频逐个检查并去字幕。」

脚本也可以单独用：

```bash
scripts/inspect-video.sh INPUT_VIDEO WORK_DIR   # 探测元数据 + 生成联系表
scripts/fetch-result.sh [--wait] OUTPUT_MP4     # 从本地日志取回已完成的结果
scripts/composite-mask.py SOURCE HITPAW RESTORED --band Y0 Y1  # 只在字幕行贴回，其余保持原片画质
scripts/conform-vertical.sh RESTORED FINAL      # 转成 1080×1920 成品
scripts/verify-clean.sh OUTPUT_VIDEO VERIFY_DIR # 成品验收（必须是 1080×1920）
```

`conform-vertical.sh` 只做交付格式转换：等比缩放到能放进 1080×1920 的最大尺寸，居中补黑边，音频直接复制，逐帧保留且会核对帧数，不覆盖已存在的文件。已经是 1080×1920 的文件直接流复制，不重新压缩；其他尺寸以 x264 CRF 16 重新编码。

`composite-mask.py` 会自己测帧对齐（偏移 -2..2 取差异最小），逐帧生成行掩码，只在这些行贴 HitPaw 的像素，其余全部来自原片；帧率、帧数、音轨都保留原片的。掩码由两部分取并集：原片的边缘扫描，加上「原片 vs HitPaw 结果」的逐帧差分。被 HitPaw 重绘过的行就是有字的行，所以差分能补上边缘扫描漏掉的无描边白字。

`fetch-result.sh --wait` 用于任务还在跑的时候等待，不带 `--wait` 用于取回已经完成的结果。**下载失败从来不构成重新提交的理由**，先取回。

## 几个必须知道的坑

**HitPaw 后端硬顶 1080。** 竖屏 720×1280、1080×1920 都会被压成 608×1080，导出设置改不掉。所以顺序固定为两步：

1. **先回到原片分辨率。** 擦除带较窄时用合成法：源片当底，只把擦除带放大后贴回，边缘羽化过渡，带外像素 100% 来自源片；贴之前先验帧对齐。整帧擦除时只能整帧放大，要明说画面是重建的。
2. **再转成 1080×1920 交付。** 用 `conform-vertical.sh`。

不要跳过第 1 步直接把 608×1080 放大成 1080×1920：成品尺寸一样，但原片里本来保得住的细节全丢了。

**边缘扫描看不见无描边的白字。** 检测靠的是字幕黑色描边产生的锐利边缘。纯白、没描边的小字压在浅色盘子或不锈钢锅上，几乎没有边缘，严格扫描直接报空。2026-09-23 那条早午餐视频里有三条这样的字（芝麻盐、撒芝士、煎几个饺子）严格扫描都没扫到，第一版成品里「芝麻盐」还留着。对策：
- 定框前再跑一遍 30fps、行阈值 15 的宽松扫描。它会把水珠、虾须、瓶口也报出来，只用来指出要人眼看的帧。
- 合成时用 `composite-mask.py`，由它的差分掩码兜底。不要只拿边缘扫描做掩码。
- 验收时两遍扫描都跑，宽松扫描报出来的每一段都要截原片和成品的对比图人眼确认。

**字幕小而分散时：一个高框 + Remove text，一次任务搞定。** 面板上的模式是 Remove watermark / **Remove text** / Remove mosaic / Quick blur，没有「Remove subtitles」。Remove text 只重绘它识别出的文字，包装袋、瓶身上的字会保留。所以框可以拉得又高又宽（例如 y≈460–1720 全宽），反正合成时只贴字幕行，框大不损画质。

**合成时别用 `-shortest`。** 原片音轨常比视频短几毫秒，`-shortest` 会悄悄砍掉最后几帧。`composite-mask.py` 用的是 `-frames:v` 原片帧数。

**`conform-vertical.sh` 不覆盖已存在的成品。** 重跑前先删旧的 FINAL，否则后面验收的是旧文件。

**导入对话框的 Go-to 栏别用粘贴。** `cmd+v` 在 09-15 和 09-23 两次都没生效，栏里还是上一个任务的路径，这时直接回车会导入别的视频。改成 `cmd+a` 后直接 type 路径，确认读到的路径对了再回车。

**1080P 确认框后台点不动。** 它被报成另一个进程的窗口，后台点击会被拒绝，需要一次前台点击 Confirm，点完立即交还控制。点第二次之前先查日志，确认任务还没提交，避免重复扣费。

**联系表不能用来量位置。** 缩到缩略图尺寸后，低对比度的那条字幕是看不见的，而位置离群的那条恰恰就是它。必须整幅高度扫描，细节见 [references/subtitle-scan.md](references/subtitle-scan.md)。

**一个任务只能框一个区域。** 画面空白处拖动、右键都加不出第二个框。字幕分在两处且相距较远时（例如全片底部字幕加开头几帧标题），不要用一个大框把中间的画面也一起重绘：主任务框一处，另一处截成单独片段再提交一次，各自只在自己的遮罩和帧段里合成回去。片段至少 2 秒，否则导入会被拒；2.5 秒约扣 3 点。画框前先双击标题栏把窗口最大化，小窗口下一个屏幕点约等于八个源像素。

**擦除框的四个角点是移动整个框，不是缩放。** 即使精准抓在角上也一样。缩放只能用四条边的中点手柄，每拖一次都要回读确认，判断依据是宽高有没有保持不变。

**结果 URL 有两个日志标记。** 正常是 `removeWatermark result url:`，App 自己下载失败时写的是 `FileReady url:`。脚本两个都匹配，取最后一条。

## 控制方式

全程走后台 app 通道，事件直接投递给 HitPaw 的窗口，不移动你的物理光标，也不把窗口提到前台。

唯一的例外是 macOS 的文件打开对话框：它属于独立系统进程 `com.apple.appkit.xpc.openAndSavePanelService`，后台通道进不去，也无法单独授权。这一步用键盘完成，四个按键、约一秒，期间键盘焦点归对话框。skill 要求在按之前先告知，而不是按完再说。详见 [references/hitpaw-gui.md](references/hitpaw-gui.md)。

## 安全与隐私

- 源文件只读，所有中间产物写到调用方指定的工作目录。
- 仓库里不保存 API key、签名 URL、任务 UUID、额度余额、用户名、源视频、截图或日志。
- 临时 URL 只存在于进程输出里，不写进清单、报告或 Git。
- 云端提交视为消耗付费额度：提交前确认文件与区域，只提交一次，绝不购买额度。
- 生成式修补可能损坏食材、手、器具、包装或界面文字。整帧擦除前必须明确警告，并单独保留未加工的原始结果以便对比。

## 局限

- 只支持 macOS 上的 HitPaw Edimakor，不是通用去字幕方案。
- 长边超过 1080 的视频会被工具降采样，这是工具的硬限制，skill 只能规避影响、不能消除。
- 成品尺寸固定为 1080×1920。横屏或非 9:16 素材会带黑边，不会自动裁切铺满；原片低于 1080×1920 时，转换只是放大，不增加细节。
- 字幕压在复杂纹理上时，生成式修补的结果需要人眼确认，脚本跑通不等于画面可用。
- 文件导入那一两秒会占用键盘焦点，无法消除。

## 许可证

MIT，见 [LICENSE](LICENSE)。

## English summary

A skill for Claude Code and Codex that drives HitPaw Edimakor on macOS to remove burned-in
subtitles and verify the result. It locates captions with a full-height per-row edge scan rather
than by eye, drives the app in background mode so the user keeps their mouse, recovers finished
jobs from the local log even when the app's own download failed, and proves coverage by re-running
the same scan on the output. Captions are pasted back through a per-frame row mask that unions the
edge scan with a source-vs-result difference, because the edge scan alone misses unstroked white
captions. Every finished file is vertical 1080x1920: the result is first restored to
the source resolution (a feathered band composite, or a disclosed full-frame upscale), then fit-scaled
onto 1080x1920 with black padding when the aspect is not 9:16, never cropped or stretched, with
audio copied and every frame kept; the verify script fails on any other size. HitPaw is a paid
dependency; this skill never purchases credits.
