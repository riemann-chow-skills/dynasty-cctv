---
name: dynasty-cctv
description: 把"古代监控录像"做成 10–30 秒的短视频——机位钉死在高处墙角，画面黑白或夜视绿，带年号时间戳、CAM 编号和机房底噪，内容是被监控拍到的古代日常（太监偷吃、大臣迟到、宫女溜号、县太爷打瞌睡）。当用户说"古代监控""监控视角的古代""古人被监控拍到""做一条古代监控视频""朝代 CCTV""古代摄像头""dynasty cctv""内务府档案"时使用。含场景案件库、文生图/图生视频 prompt 配方、年号时辰换算、ffmpeg 后期管线（OSD 时间戳 / 噪点 / 扫描线 / 信号干扰 / 底噪 / 档案卡）。
agent_created: true
---

# Dynasty CCTV · 古代监控录像

一个古代场景 + 一个监控机位 + 一件鸡毛蒜皮的小事 = 一条能被当成"出土证据"转发的东西。

产物：`mp4`（10–30 秒，带时间戳与底噪）+ 可选片尾档案卡 + 可选封面帧。

## 为什么这个形式成立

监控画面自带三重可信度：**机位是死的**（没人会为了构图摆机位）、**画质是烂的**（烂画质=未经修饰=真实）、**时间是打的**（时间戳意味着"这是一段记录"）。三者叠加，观众第一秒就默认"这是记录不是创作"，于是画面里的荒诞才成立——你看到的是"证据"，不是"段子"。

所以这条片子的全部功力，都在**维持这个假象**。任何一点电影感都会让它塌。

## 六条铁律

1. **画面必须廉价**。景深、逆光、升格、运镜、配乐——出现任何一个，形式立刻失效。目标是"像从某个系统里导出来的"。
2. **机位不许动**。5 秒里摄像机唯一的动作是噪点。不许推、拉、摇、移、变焦。
3. **一镜一事**。一个镜头里必须有一件从发生到结束（或到被发现）的小事。允许"没结束"（人还杵在那儿），不允许"什么都没发生"。
4. **一个字都不解释**。没有旁白、没有说明字幕、没有"此时……"。观众自己看懂才好笑，看懂了还要解释就不好笑了。
5. **文字全部后期烧**。年号、CAM 编号、时间戳一律由 `cctv.py` 打。prompt 里必须写 `no text, no watermark, no timestamp`——模型写字必糊，而且每一帧都不一样。
6. **荒诞要一本正经**。人物表情越正常越好。不许挤眉弄眼、不许夸张表演、不许回头看镜头。他们不知道有摄像头。

## 工作流

> **路径约定**：`$SKILL` 指本技能的绝对路径（加载技能时给出的 Base directory）。中间产物落在当前工作目录，不污染技能目录。

### 第 0 步 · 定题 + 报成本（必做）

一句话公式：

```
谁 · 在哪 · 干了什么 · 被谁看见
```

例：`一个小太监 · 御膳房东廊 · 半夜偷吃供桌上的点心 · 被总管撞见`

**动手前先说清成本**：首帧图每张约 5–10 积分，5 秒视频约 50–100 积分。一条 4 镜的片子约 4 张图 + 4 段视频，按 250–450 积分估。用户点头再开工。

选题没头绪时，去 `references/scene-library.md` 挑——那里按宫廷/衙门/市井/军营/书院/寺庙分了 32 个现成的"案件"，每条都写好了机位、事件、笑点。

### 第 1 步 · 写分镜表

3–5 个镜头，每镜 4–5 秒。写成一个表，落到 `storyboard.md`：

| 镜 | 机位 | 画面里发生什么 | 时长 | 备注 |
|---|---|---|---|---|
| 01 | 御膳房·东廊 CAM 03 | 小太监掀食盒，捏起一块点心塞嘴里 | 4s | 夜视 |
| 02 | 同上（同一机位） | 总管从廊尾走进画面，太监僵住，腮帮子鼓着 | 4s | 同一机位，时间连着 |
| 03 | 同上 | 总管盯着他看，太监把嘴里的咽下去 | 4s | 对视三秒 |

**关键**：同一个场景尽量用**同一个机位**拍完。监控不会为了拍第二件事换个角度——换机位就等于告诉观众"这是摆拍"。真要换，写成 `CAM 03 → CAM 05`，并在时间戳上保持连续。

跨场景/跨天就用 `--times` / `--days` / `--cams` 逐镜指定，时间戳会整段跳，而不是连续走：

```bash
--times "20:07,22:40,23:55,23:58,09:15" \
--days  "0,0,0,0,3" \
--cams  "01:麦城·北门,04:麦城·粮仓,07:麦城·马厩,02:麦城·城楼,01:麦城·北门"
```

时间戳只需要给**起点**，同一镜内 `cctv.py` 会自动走字（默认 60 倍速，1 秒走 1 分）。先算一下：

```bash
python3 $SKILL/scripts/cctv.py clock --dynasty 大明 --era 万历 --year 15 --month 3 --day 7 --hour 14 --minute 32
```

### 第 2 步 · 出首帧（ImageGen 文生图）

**必须先出图，再图生视频。** 文生视频十有八九给你一个电影镜头——轨道、浅景深、暖光，全是这个形式的天敌。图生视频能把机位、画质、光线锁死。

按 `references/prompt-recipes.md` 的五段式写英文 prompt：

```
[1 机位]  high corner security camera, wide-angle lens, 30° downward tilt, static
[2 场景]  朝代建筑细节 + 空间关系
[3 主体]  人物 + 朝代服饰 + 一个定格动作
[4 光质]  flat even lighting, no shadows, low dynamic range
[5 质感]  grainy, soft focus, low resolution, security footage still
[负向]    no text, no timestamp, no watermark, no logo, no cinematic lighting
```

`size` 用 `1536x1024`（16:9）或 `1024x1024`（方图，裁成 4:3 更复古）。**出图后一定用 Read 打开看一眼**：服饰对不对、有没有眼镜手表、模型有没有偷偷画时间戳。

### 第 3 步 · 出动态（VideoGen 图生视频）

prompt 只写**变化**，不写画面（画面已经在图里了，重复描述会诱导重绘）：

```
Static camera, no movement. The young eunuch lifts the food box lid, takes a piece of
pastry and eats it quickly. A supervisor walks in from the far end of the corridor.
The eunuch freezes with full cheeks and stands straight. Same framing, same lighting,
same grainy low-quality look.
```

| 参数 | 怎么填 |
|---|---|
| `image` | 第 2 步的图（绝对路径） |
| `prompt` | 上面这段，60–100 词英文 |
| `negative_prompt` | `camera movement, pan, zoom, dolly, cinematic lighting, shallow depth of field, text, watermark, face morphing, extra fingers` |
| `seconds` | `4` 或 `5`；模型不接受自定义就省略 |
| `resolution` | `720P` 够用（反正后期要降清），要更糊就 480P |
| `enable_audio` | **`false`**。模型给的环境音常带配乐，后期统一加机房底噪 |
| `aspect_ratio` | **不要传**，图生视频由图片比例决定 |

生成要 1–3 分钟，不要重复调用，等结果。

### 第 4 步 · 后期（一条命令出片）

```bash
python3 $SKILL/scripts/cctv.py join shots/*.mp4 -o 成片.mp4 \
  --size 1280x720 \
  --cam "御膳房·东廊" --cam-no 03 \
  --dynasty 大明 --era 万历 --year 15 --month 3 --day 7 --hour 14 --minute 32 \
  --watermark "内务府档案" --grade night --glitch --tail card.mp4
```

> `--size` 不是可选项。不传的话 `join` 会沿用第一个镜头的原始比例（通常是 3:2），既不统一，也裁不掉生成工具留在四角的水印。

这一条命令干了七件事：统一尺寸帧率 → 拼接 → 低清化 → 调色 → 噪点 → 暗角扫描线 → 烧连续时间戳 → 加底噪 → 接片尾卡。

先只想看效果、不想接片尾卡，就去掉 `--tail`。

### 第 5 步 · 片尾档案卡

把"AI 生成"变成"出土证据"的那一下，就靠这张卡：

```bash
python3 $SKILL/scripts/cctv.py card -o card.mp4 \
  --line1 "内务府档案" \
  --line2 "卷三一七 · 万历十五年三月初七" \
  --line3 "御膳房 东廊 · CAM 03"
```

三行字的写法见 `references/osd-spec.md`：第一行是存档单位，第二行是卷号+日期，第三行是机位。**卷号要像真的**——「卷三一七」比「第 1 号」可信十倍。

### 第 6 步 · 质检与交付

```bash
# 抽帧拼图，一眼看全片
python3 $SKILL/scripts/cctv.py sheet 成片.mp4 -o 质检.jpg
# 封面帧（同一套质感，但不带噪点闪烁）
python3 $SKILL/scripts/cctv.py still shots/01.png -o 封面.jpg --grade night
```

按 `references/qa-checklist.md` 过一遍。交付 `成片.mp4` + `封面.jpg`，用 present_files 一起给。

## 参数速查

| 想要的效果 | 参数 |
|---|---|
| 白天室内走廊 | `--grade color`（默认） |
| 老 DVR 黑白 | `--grade gray` |
| 夜巡 / 红外夜视 | `--grade night` |
| 老磁带泛黄 | `--grade sepia` |
| 更像十几年前的机器 | `--size 960x540 --lowres 3 --fps 15` |
| 复古 4:3 | `--size 1024x768` |
| 竖屏发抖音 | `--size 1080x1920 --fit crop`（OSD 会自动按高度缩放） |
| 信号干扰闪两下 | `--glitch` |
| 静音 | `--audio none` |
| 保留模型环境音 | `--audio keep` |
| 环境音 + 底噪混 | `--audio mix` |
| 时间戳用现代时分秒 | `--clock-style modern` |
| 跨天/跨时辰跳时 | `--times "20:07,22:40,09:15" --days "0,0,3"` |
| 逐镜换机位 | `--cams "01:北门,04:粮仓,07:马厩"` |
| 绿色 OSD（老监控） | `--osd-color green` |
| 不要闪烁红点 | `--no-rec` |

## 机位语法

监控机位的选择不是构图问题，是**"这个位置为什么会装摄像头"**的问题。

| 机位 | 位置与角度 | 适合拍什么 |
|---|---|---|
| 墙角高位 | 房梁/墙角，俯角 30–45°，广角 | 走廊、库房、院子——最通用，默认选它 |
| 门楣正对 | 门框上方，正对通道 | 进出、迟到、溜号、撞见 |
| 院墙对角 | 院子对角，拍全场 | 群体事件、排队、操练 |
| 柜台后 | 齐胸高度，平视 | 交易、争执、偷换 |
| 梁下逆光 | 仓房/马厩梁下，逆光剪影 | 偷盗、私下交易 |
| 城墙垛口 | 极高俯角，拍墙根 | 巡逻、夜更、翻墙 |

## 常见翻车

| 症状 | 原因 | 怎么修 |
|---|---|---|
| 画面右上角有个摄像头 | prompt 写了 `a camera mounted above...`，模型把摄像头当物体画了 | 改成 `View from a high corner surveillance camera looking down at...`，并加 `no camera housing visible` |
| 一眼假 | 有景深/暖光/运镜 | 重出首帧，prompt 里加 `flat lighting, everything in focus, static, plain off-centre framing` |
| 太清楚 | 模型给的是高清素材 | `--lowres 3 --fps 15`，噪点提到 18 |
| 人物穿帮 | 眼镜、手表、拉链、运动鞋 | 首帧 prompt 写死朝代服饰，出图后逐个看 |
| 画面里有一坨假字 | 模型自己画了时间戳/匾额 | 重出；匾额改用 `blank plaque`，字全部后期打 |
| 四角有"AI生成"水印 | 没传 `--size`，`join` 沿用了首镜的原始比例，没裁到 16:9 | **永远带 `--size 1280x720`**，裁切会顺手把水印切掉 |
| 镜头在动 | 图生视频默认会轻微推近 | prompt 开头写 `Static camera, no movement`，negative 加 `camera movement` |
| 人像变脸 | 图生视频通病 | 动作幅度减小，只让人走两步、抬一次手 |
| 时间戳和画面对不上 | 夜里写了白天 | 夜视画面必须配夜里的时辰（见 osd-spec） |
| 太安静/太空 | 没有底噪 | 默认 `--audio bed`，别关 |
| `429 Credits exhausted` | 积分用完，不是限流，重试没用 | 见下面「额度不够时的降级出片」，先把已成功的片段改名存好 |

## 额度不够时的降级出片

VideoGen 报 `429 / code 14018 / Credits exhausted` 是**积分耗尽**，不是并发限流，重试多少次都不会成功。别重复提交（成功的片段也会浪费额度），已经落盘的先重命名保存。

缺的镜头用**首帧静帧**顶上。监控形式本来就允许近乎静止（L1 微动），逐帧噪点、扫描线、掉帧和走字时间戳会撑住"这是录像"，成片观感差别很小：

```bash
# 与 VideoGen 产物对齐：1176×784（3:2）/ 24fps / 4.04s
ffmpeg -hide_banner -loglevel error -y -loop 1 -framerate 24 -i 首帧.png \
  -frames:v 97 -vf "scale=1176:784,setsar=1,format=yuv420p" \
  -c:v libx264 -crf 18 -pix_fmt yuv420p -movflags +faststart shotN.mp4
```

静帧片段**不要自己加噪点**：`join` 的 `noise=allf=t+u` 本来就是逐帧变的，正好是机器底噪。之后照常 `join --size 1280x720`。

用户补足额度后，只重跑缺的那几段视频、同名替换 `shotN.mp4`、再 `join` 一次即可，**首帧和分镜表都不用重做**。交付时如实说明哪几镜是静帧。

> ImageGen/VideoGen 并行调用还有两个坑：同秒会撞文件名（前缀+时间戳），`output_dir` 在并发下也可能串到同一个目录。要么串行，要么每路给不同 `output_dir`、prompt 开头写成不同单词，事后按返回路径逐个改名。

## 系列化玩法（用户说"还想多做几条"时提）

1. **同一机位 24 小时**：一个走廊机位，卯时/午时/申时/子时四段拼起来，时间戳连续递进。最有"档案感"。
2. **跨朝代同机位**：唐/宋/明/清 同一个"御膳房走廊"，服化道全换，机位编号不变。适合做合集封面。
3. **铁证如山**：同一个机位拍到三个人做同一件事（都来偷吃），第三条被逮住。
4. **监控盲区**：人走出画面，两秒后画面外传来一声响，人抱着东西跑回来。画外音比画内戏好笑。
5. **对照组**：白天版（正常）＋ 夜里版（夜视），同一件事两种画质。
6. **"上级来查"**：一整排人站得笔直，最边上一个在偷偷系腰带。

## 脚本

| 脚本 | 干什么 |
|---|---|
| `scripts/cctv.py clock` | 年号/农历/干支/时辰刻分换算，写分镜表用 |
| `scripts/cctv.py join` | **主命令**：多镜头拼接 + 连续时间戳 + 监控质感 + 底噪 + 片头片尾 |
| `scripts/cctv.py look` | 单条片段套质感（可带 OSD），试参数用 |
| `scripts/cctv.py card` | 片尾档案卡 |
| `scripts/cctv.py still` | 静帧套质感，出封面 |
| `scripts/cctv.py sheet` | 抽帧拼图，质检 |
| `scripts/cctv.py osd` | 只生成时间戳字幕文件，调样式用 |
| `scripts/cctv.py probe` | 看视频信息 |

`cctv.py` 依赖 ffmpeg 与 fontconfig 中文字体。ffmpeg 会自动去 `FFMPEG_BINARY`、imageio-ffmpeg、Homebrew 路径找；找不到就提示 `brew install ffmpeg`。字体自动在系统里挑可用的中文字族（Heiti SC / PingFang SC / Songti SC…），也可以用 `--font` 指定。

## 参考文档

| 文件 | 什么时候读 |
|---|---|
| `references/scene-library.md` | 选题没头绪 / 要 32 个现成案件 |
| `references/prompt-recipes.md` | 写首帧和视频 prompt 之前 |
| `references/osd-spec.md` | 定年号、宫署名、卷号、CAM 编号时 |
| `references/qa-checklist.md` | 交付前 |
