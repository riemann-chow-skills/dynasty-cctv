# dynasty-cctv

把「古代监控录像」做成 10–30 秒的短视频。

机位钉死在高处墙角，画面黑白或夜视绿，带年号时间戳、CAM 编号和机房底噪——内容是被监控拍到的古代日常：太监偷吃、大臣迟到、宫女溜号、县太爷打瞌睡。

```
谁 · 在哪 · 干了什么 · 被谁看见
一个小太监 · 御膳房东廊 · 半夜偷吃点心 · 被总管撞见
```

## 装

```bash
ln -s /Users/Riemann/Code/skills/dynasty-cctv ~/.workbuddy-ai/skills/dynasty-cctv
```

依赖 `ffmpeg`（`brew install ffmpeg`）和系统里的中文字体。

## 用

```bash
# 1. 换算时间戳
python3 scripts/cctv.py clock --dynasty 大明 --era 万历 --year 15 --month 3 --day 7 --hour 14 --minute 32

# 2. 出片（多镜头拼接 + 时间戳 + 监控质感 + 底噪 + 片尾卡）
python3 scripts/cctv.py join shots/*.mp4 -o 成片.mp4 \
  --cam "御膳房·东廊" --cam-no 03 \
  --dynasty 大明 --era 万历 --year 15 --month 3 --day 7 --hour 14 --minute 32 \
  --watermark "内务府档案" --grade night --glitch --tail card.mp4

# 3. 片尾档案卡
python3 scripts/cctv.py card -o card.mp4 --line1 内务府档案 \
  --line2 "卷三一七 · 万历十五年三月初七" --line3 "御膳房 东廊 · CAM 03"
```

## 结构

```
SKILL.md                      工作流与六条铁律
references/scene-library.md   32 个现成「案件」
references/prompt-recipes.md  首帧 / 视频 prompt 配方 + 朝代服化道速查
references/osd-spec.md        年号、时辰、宫署名、CAM 编号、档案卡写法
references/qa-checklist.md    交付前质检
scripts/cctv.py               后期管线：clock / osd / look / join / still / card / sheet / probe
```

## 核心判断

监控质感不是滤镜，是六件套：**低清糊 + 噪点 + 扫描线 + 暗角 + 掉帧 + 时间戳**。

这六件里，前五件模型能画个七八分，**第六件必须自己烧**——模型写不好中文，而且每一帧写的都不一样。所以流程永远是：模型出画面，`cctv.py` 出文字。
