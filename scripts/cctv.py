#!/usr/bin/env python3
"""dynasty-cctv · 古代监控视频的确定性后期管线

监控质感不是"滤镜感"，是六件套叠出来的：
  低清糊（降采样再上采样）+ 噪点 + 扫描线 + 暗角 + 掉帧 + 时间戳 OSD

这些必须用 ffmpeg 烧，不能指望视频模型画——模型画中文必糊，
画出来的时钟不走，画出来的 CAM 编号每一帧都不一样。

子命令：
    clock   年号 / 农历日 / 干支 / 时辰刻分 换算，写分镜表用
    osd     生成监控时间戳字幕文件（.ass），可单独调试
    look    给单条片段套监控质感（可同时烧 OSD）
    join    多条镜头拼接 → 连续时间戳 → 底噪 → 成片
    still   给静帧套同一套质感（封面 / 首帧 / 缩略图）
    card    片尾档案标签卡（黑底白字 + 扫描线）
    sheet   抽帧拼图，快速质检
    probe   查看视频信息

示例：
    python3 cctv.py clock --dynasty 大明 --era 万历 --year 15 --month 3 --day 7 --hour 14 --minute 32
    python3 cctv.py join shots/*.mp4 -o 成片.mp4 --cam "御膳房·东廊" --cam-no 03 \
        --dynasty 大明 --era 万历 --year 15 --month 3 --day 7 --hour 14 --minute 32
    python3 cctv.py look 片段.mp4 -o 处理.mp4 --grade night
    python3 cctv.py card -o 卡.mp4 --line1 "内务府档案" --line2 "卷三一七 · 万历十五年三月初七"

ffmpeg 找不到时会自动去 FFMPEG_BINARY、imageio-ffmpeg、Homebrew 路径里找。
"""

import argparse
import glob
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta

# ---------------------------------------------------------------- ffmpeg 定位


def find_ffmpeg(explicit=None):
    for cand in (explicit, os.environ.get("FFMPEG_BINARY"), shutil.which("ffmpeg")):
        if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    try:
        import imageio_ffmpeg  # type: ignore

        p = imageio_ffmpeg.get_ffmpeg_exe()
        if p and os.path.isfile(p):
            return p
    except Exception:
        pass
    patterns = [
        os.path.expanduser("~/.workbuddy-ai/binaries/python/envs/*/lib/python*/site-packages/imageio_ffmpeg/binaries/ffmpeg-*"),
        os.path.expanduser("~/Library/Python/*/lib/python/site-packages/imageio_ffmpeg/binaries/ffmpeg-*"),
        "/opt/homebrew/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "/usr/bin/ffmpeg",
    ]
    for pat in patterns:
        for p in glob.glob(pat):
            if os.path.isfile(p) and os.access(p, os.X_OK):
                return p
    return None


FFMPEG = None
DRY = False


def need_ffmpeg():
    global FFMPEG
    if FFMPEG:
        return FFMPEG
    FFMPEG = find_ffmpeg()
    if not FFMPEG:
        sys.exit(
            "找不到 ffmpeg。任选一种装上后重试：\n"
            "  brew install ffmpeg\n"
            "  pip install imageio-ffmpeg        # 自带一份二进制，无需系统权限\n"
        )
    return FFMPEG


def run(args, cwd=None, quiet=True):
    cmd = [need_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y"] + args
    if DRY:
        print("  " + " ".join(cmd))
        return ""
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if p.returncode != 0:
        tail = (p.stderr or "").strip().splitlines()[-8:]
        sys.exit("ffmpeg 失败：\n  " + "\n  ".join(tail))
    return p.stderr or ""


def probe(path):
    """没有 ffprobe 也要能读时长/分辨率/音轨，直接啃 ffmpeg -i 的 stderr。"""
    if not os.path.isfile(path):
        sys.exit(f"文件不存在：{path}")
    p = subprocess.run([need_ffmpeg(), "-hide_banner", "-i", path], capture_output=True, text=True)
    text = (p.stderr or "") + (p.stdout or "")
    info = {"file": os.path.abspath(path), "bytes": os.path.getsize(path), "audio": False}
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", text)
    if m:
        info["duration"] = round(int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)), 3)
    m = re.search(r"Video:.*?,\s*(\d{2,5})x(\d{2,5})", text)
    if m:
        info["width"], info["height"] = int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d+\.?\d*)\s*fps", text)
    if m:
        info["fps"] = float(m.group(1))
    info["audio"] = "Audio:" in text
    return info


def duration_of(path):
    d = probe(path).get("duration")
    if not d:
        sys.exit(f"读不到时长：{path}")
    return d


# ------------------------------------------------------------ 年号 / 时辰换算

DIGITS = "零一二三四五六七八九"
SHICHEN = "子丑寅卯辰巳午未申酉戌亥"
GAN = "甲乙丙丁戊己庚辛壬癸"
ZHI = "子丑寅卯辰巳午未申酉戌亥"


def cn_num(n):
    """1..9999 → 汉字（十五 / 三十七 / 一千五百八十七）"""
    n = int(n)
    if n < 0:
        return str(n)
    if n == 0:
        return "零"
    if n < 10:
        return DIGITS[n]
    if n < 20:
        return "十" + (DIGITS[n % 10] if n % 10 else "")
    units = [(1000, "千"), (100, "百"), (10, "十")]
    out, rest, zero = "", n, False
    for base, name in units:
        d = rest // base
        rest %= base
        if d:
            out += DIGITS[d] + name
            zero = False
        elif out and rest:
            zero = True
    if rest:
        out += ("零" if zero else "") + DIGITS[rest]
    return out


def cn_month(m):
    m = int(m)
    return {1: "正月", 11: "冬月", 12: "腊月"}.get(m, cn_num(m) + "月")


def cn_day(d):
    d = int(d)
    if d <= 10:
        return "初" + DIGITS[d]
    if d < 20:
        return "十" + DIGITS[d % 10]
    if d == 20:
        return "二十"
    if d < 30:
        return "廿" + DIGITS[d % 10]
    if d == 30:
        return "三十"
    return cn_num(d)


def ganzhi(year):
    """干支纪年（公元年份，1587 → 丁亥）"""
    y = int(year)
    return GAN[(y - 4) % 10] + ZHI[(y - 4) % 12]


# 常见年号 → 元年公元年，用来推干支。表里没有就用 --ad-year 手动指定。
ERA_START = {
    "建元": -140, "元狩": -122, "太初": -104, "始元": -86,
    "建武": 25, "永平": 58, "建安": 196,
    "黄初": 220, "太和": 227, "青龙": 233,
    "章武": 221, "建兴": 223, "延熙": 238, "景耀": 258, "炎兴": 263,  # 蜀汉
    "黄武": 222, "黄龙": 229, "嘉禾": 232, "赤乌": 238,               # 孙吴
    "泰始": 265, "永嘉": 307,
    "开皇": 581, "大业": 605, "武德": 618,
    "贞观": 627, "永徽": 650, "显庆": 656, "龙朔": 661,
    "开元": 713, "天宝": 742, "至德": 756, "大历": 766,
    "建中": 780, "元和": 806, "会昌": 841, "大中": 847,
    "乾符": 874, "中和": 881, "天祐": 904,
    "建隆": 960, "太平兴国": 976, "咸平": 998, "天圣": 1023,
    "庆历": 1041, "熙宁": 1068, "元丰": 1078, "元祐": 1086,
    "崇宁": 1102, "宣和": 1119, "靖康": 1126,
    "绍兴": 1131, "淳熙": 1174, "嘉定": 1208, "咸淳": 1265,
    "洪武": 1368, "建文": 1399, "永乐": 1403, "洪熙": 1425,
    "宣德": 1426, "正统": 1436, "景泰": 1450, "天顺": 1457,
    "成化": 1465, "弘治": 1488, "正德": 1506, "嘉靖": 1522,
    "隆庆": 1567, "万历": 1573, "泰昌": 1620, "天启": 1621, "崇祯": 1628,
    "天命": 1616, "天聪": 1627, "崇德": 1636,
    "顺治": 1644, "康熙": 1662, "雍正": 1723, "乾隆": 1736,
    "嘉庆": 1796, "道光": 1821, "咸丰": 1851, "同治": 1862,
    "光绪": 1875, "宣统": 1909,
}


def ad_year_of(a):
    """年号第 N 年 → 公元年。查表失败返回 None。"""
    if getattr(a, "ad_year", None):
        return int(a.ad_year)
    start = ERA_START.get(getattr(a, "era", "") or "")
    if start is None:
        return None
    return start + int(a.year) - 1


def shichen(hour, minute):
    """现代钟点 → (时辰, 刻, 分)。一昼夜 96 刻，一时辰 8 刻，一刻 15 分。"""
    hour, minute = int(hour) % 24, int(minute) % 60
    idx = ((hour + 1) // 2) % 12
    start = (idx * 2 - 1) % 24
    offset = ((hour - start) % 24) * 60 + minute
    return SHICHEN[idx], offset // 15 + 1, offset % 15


def format_date(a, day_shift=0):
    """日期行：大明·万历十五年 三月初七 丁亥"""
    era = f"{a.era}{cn_num(a.year)}年" if a.era else f"{cn_num(a.year)}年"
    left = f"{a.dynasty}·{era}" if a.dynasty else era
    tail = []
    if a.month:
        tail.append(cn_month(a.month) + cn_day(a.day + day_shift))
    if a.ganzhi:
        ad = ad_year_of(a)
        if ad:
            tail.append(ganzhi(ad))
    return left + (" " + " ".join(tail) if tail else "")


def format_clock(a, dt):
    """时间行：未时五刻 二分 / 14:32:07"""
    if a.clock_style == "modern":
        return dt.strftime("%H:%M:%S")
    sc, ke, fen = shichen(dt.hour, dt.minute)
    txt = f"{sc}时{cn_num(ke)}刻"
    return txt + (f" {cn_num(fen)}分" if fen else "")


# ------------------------------------------------------------------ 字体挑选

FONT_CANDIDATES = [
    "Heiti SC",
    "PingFang SC",
    "Hiragino Sans GB",
    "Source Han Sans SC",
    "Noto Sans CJK SC",
    "Songti SC",
    "Microsoft YaHei",
    "Arial Unicode MS",
]


def pick_font(preferred=None):
    """libass 靠 fontconfig 找字，名字必须真实存在，否则整片变豆腐块。"""
    fams = set()
    try:
        out = subprocess.run(["fc-list", ":lang=zh", "family"], capture_output=True, text=True).stdout
        for line in out.splitlines():
            for f in line.split(","):
                if f.strip():
                    fams.add(f.strip())
    except Exception:
        pass
    cands = ([preferred] if preferred else []) + FONT_CANDIDATES
    for c in cands:
        if c in fams:
            return c
    return preferred or "Heiti SC"


# --------------------------------------------------------------- OSD 字幕生成

ASS_HEADER = """[Script Info]
; generated by dynasty-cctv
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: OSD,{font},{size},&H00{pri},&H00{pri},&H00000000,&H00000000,0,0,0,0,100,100,1.2,0,1,2,0,7,0,0,0,1
Style: CAM,{font},{size2},&H00{pri},&H00{pri},&H00000000,&H00000000,0,0,0,0,100,100,1.2,0,1,2,0,9,0,0,0,1
Style: SMALL,{font},{size3},&H00{pri},&H00{pri},&H00000000,&H00000000,0,0,0,0,100,100,0.8,0,1,1,0,1,0,0,0,1
Style: CARD,{font},{cardsize},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,4,0,1,1,0,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

OSD_COLORS = {
    "white": "FFFFFF",
    "green": "78FF78",
    "amber": "3CBEFF",  # ASS 是 BGR：BB=3C GG=BE RR=FF → 琥珀色
    "cyan": "EED8C8",
}


def ass_time(t):
    t = max(0.0, float(t))
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


BASE_DATE = datetime(2000, 1, 1)


def seg(t0, t1, dt, cam_no="", cam=""):
    """一个时间戳分段：时间轴 [t0,t1)，从 dt 起按倍速走字，机位可单独指定。"""
    return {"t0": float(t0), "t1": float(t1), "dt": dt, "cam_no": cam_no, "cam": cam}


def build_ass(path, w, h, segments, args, font):
    """按秒切事件，让时间戳真的在走。CCTV 的时钟不走，一眼假。

    分段是为了跳时：监控素材经常是「同一台机器，三天后再看」，
    这时候时间戳必须整段跳，不能连续走。
    """
    # 字号跟"短边"走：竖屏用高度算会把字放到互相撞车
    base = min(w, h)
    size = max(12, int(round(base * 0.0305 * args.osd_scale)))
    size2 = max(11, int(round(base * 0.0255 * args.osd_scale)))
    size3 = max(9, int(round(base * 0.0195 * args.osd_scale)))
    cardsize = max(20, int(round(base * 0.058 * args.osd_scale)))
    pri = OSD_COLORS.get(args.osd_color, "FFFFFF")
    pad = max(10, int(round(base * 0.042)))

    body = []
    for sg in segments:
        cam_no = sg.get("cam_no") or args.cam_no
        cam = sg.get("cam") or args.cam
        s = 0
        while True:
            tt0 = sg["t0"] + s
            if tt0 >= sg["t1"] - 1e-6:
                break
            tt1 = min(tt0 + 1, sg["t1"])
            dt = sg["dt"] + timedelta(seconds=s * args.clock_speed)
            day_shift = (dt.date() - BASE_DATE.date()).days
            left = f"{format_date(args, day_shift)}\\N{format_clock(args, dt)}"
            body.append(f"Dialogue: 0,{ass_time(tt0)},{ass_time(tt1)},OSD,,0,0,0,,{{\\pos({pad},{pad})}}{left}")

            if cam_no or cam:
                cam_txt = f"CAM {cam_no}" if cam_no else "CAM"
                if cam:
                    cam_txt += f"\\N{cam}"
                rec = ""
                if args.rec and int(tt0) % 2 == 0:
                    rec = "{\\c&H000000FF&}●{\\c&H" + pri + "&} "
                body.append(
                    f"Dialogue: 0,{ass_time(tt0)},{ass_time(tt1)},CAM,,0,0,0,,{{\\pos({w - pad},{pad})}}{rec}{cam_txt}"
                )

            if args.watermark:
                body.append(
                    f"Dialogue: 0,{ass_time(tt0)},{ass_time(tt1)},SMALL,,0,0,0,,"
                    f"{{\\pos({pad},{h - pad})\\an1}}{args.watermark}"
                )
            s += 1

    head = ASS_HEADER.format(w=w, h=h, font=font, size=size, size2=size2, size3=size3, cardsize=cardsize, pri=pri)
    with open(path, "w", encoding="utf-8") as f:
        f.write(head + "\n".join(body) + "\n")
    return path


# ------------------------------------------------------------- 监控质感滤镜链

GRADES = {
    # 彩色但褪色，偏冷，像便宜的 CMOS
    "color": "eq=contrast=1.10:brightness=-0.012:saturation=0.32,colorbalance=bs=0.045:gs=0.015:rs=-0.01",
    # 老 DVR 的黑白
    "gray": "format=gray,eq=contrast=1.16:brightness=-0.015",
    # 夜视红外：绿得发灰
    "night": "format=gray,colorchannelmixer=rr=0.18:gg=1.02:bb=0.18,eq=contrast=1.20:brightness=0.035",
    # 泛黄的老磁带
    "sepia": "colorbalance=rs=0.22:gs=0.09:bs=-0.16:rm=0.12:gm=0.05:bm=-0.08,eq=saturation=0.42:contrast=1.12",
}


def look_chain(w, h, args, tail="", temporal=True):
    """低清 → 调色 → 噪点 → 暗角 → 扫描线。顺序不能乱。"""
    f = []
    if args.fit == "crop":
        f.append(f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}")
    else:
        f.append(f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black")
    f.append("setsar=1")
    if args.fps:
        f.append(f"fps={args.fps}")
    if args.lowres > 1:
        dw = max(2, w // args.lowres // 2 * 2)
        f.append(f"scale={dw}:-2:flags=bilinear")
        f.append(f"scale={w}:{h}:flags=bilinear")
    f.append(GRADES.get(args.grade, GRADES["color"]))
    if args.noise > 0:
        f.append(f"noise=alls={args.noise}:allf={'t+u' if temporal else 'u'}")
    if args.vignette > 0:
        f.append(f"vignette=angle=PI/{args.vignette:.2f}")
    if args.scanlines > 0:
        f.append(f"drawgrid=w=iw:h={args.scanlines}:t=1:color=black@{args.scanline_alpha}")
    f.append("format=yuv420p")
    chain = ",".join(f)
    if not tail:
        return chain
    return chain + "," + tail


def glitch_tail(w, h, dur, args):
    """信号干扰：在指定位置插 0.12s 纯雪花，两次。"""
    if not args.glitch or dur < 3:
        return None, None
    a1 = dur * 0.31
    a2 = dur * 0.73
    wins = f"between(t,{a1:.2f},{a1 + 0.12:.2f})+between(t,{a2:.2f},{a2 + 0.12:.2f})"
    src = (
        f"color=c=0x5a5a5a:s={w}x{h}:r={args.fps or 25}:d={dur + 1:.2f},"
        f"noise=alls=80:allf=t,format=gray[gl]"
    )
    return src, wins


# ------------------------------------------------------------------ 音频底噪


def audio_bed(dur, args):
    """机房底噪：粉噪 + 一点电流嗡鸣。没有这个，AI 视频的"干净"会出卖它。"""
    base = (
        f"anoisesrc=color=pink:amplitude={args.bed_level}:r=48000,"
        f"highpass=f=110,lowpass=f=6800"
    )
    if args.hum <= 0:
        return base
    return (
        f"{base}[bed];sine=f=50:r=48000,volume={args.hum}[hum];"
        f"[bed][hum]amix=inputs=2:duration=first:normalize=0"
    )


# -------------------------------------------------------------------- 子命令


def cmd_probe(a):
    info = probe(a.input)
    if a.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return
    print(f"\n▸ {os.path.basename(info['file'])}")
    if "width" in info:
        print(f"  {info['width']}×{info['height']}  {info.get('fps', '?')}fps")
    print(f"  时长 {info.get('duration', '?')}s   音轨 {'有' if info['audio'] else '无'}   {info['bytes'] / 1048576:.2f}MB")


def cmd_clock(a):
    sc, ke, fen = shichen(a.hour, a.minute)
    ad = ad_year_of(a)
    print("\n▸ 时间换算")
    print(f"  日期   {format_date(a)}")
    if ad:
        print(f"  干支   {ganzhi(ad)}年   （公元 {ad} 年）")
    else:
        print("  干支   ——   年号不在内置表里，加 --ad-year 1587 可补干支")
    print(f"  时辰   {sc}时 {cn_num(ke)}刻 {cn_num(fen)}分   （{a.hour:02d}:{a.minute:02d} 起）")
    print(f"  时间行 {format_clock(a, datetime(2000, 1, 1, a.hour, a.minute))}")
    print("\n  提示：一时辰 8 刻，一刻 15 分；OSD 默认按 60 倍速走字，20 秒片长约走 20 分。")


def cmd_osd(a):
    w, h = parse_size(a.size)
    font = pick_font(a.font)
    out = a.output or "osd.ass"
    build_ass(out, w, h, [seg(0, a.duration, datetime(2000, 1, 1, a.hour, a.minute))], a, font)
    print(f"✓ {out}   字体 {font}   {w}×{h}   {a.duration}s")


def parse_size(s):
    m = re.match(r"(\d+)x(\d+)", s or "")
    if not m:
        sys.exit("--size 要写成 1280x720 这样")
    return int(m.group(1)), int(m.group(2))


def cmd_look(a):
    info = probe(a.input)
    w, h = (parse_size(a.size) if a.size else (info.get("width", 1280), info.get("height", 720)))
    w, h = w - w % 2, h - h % 2
    dur = info.get("duration", 5.0)
    font = pick_font(a.font)

    ass_name = None
    if a.osd:
        tmpdir = os.path.dirname(os.path.abspath(a.output)) or "."
        ass_name = "_osd_look.ass"
        build_ass(os.path.join(tmpdir, ass_name), w, h,
                  [seg(0, dur, datetime(2000, 1, 1, a.hour, a.minute))], a, font)

    chain = look_chain(w, h, a)
    gsrc, gwin = glitch_tail(w, h, dur, a)
    if gsrc:
        fc = f"[0:v]{chain}[base];{gsrc};[base][gl]overlay=enable='{gwin}':shortest=1[vg]"
        if ass_name:
            fc += f";[vg]subtitles={ass_name}[v]"
            out_label = "v"
        else:
            out_label = "vg"
    else:
        if ass_name:
            fc = f"[0:v]{chain},subtitles={ass_name}[v]"
            out_label = "v"
        else:
            fc = f"[0:v]{chain}[v]"
            out_label = "v"

    args = ["-i", os.path.abspath(a.input)]
    if a.audio != "none":
        args += ["-f", "lavfi", "-t", f"{dur:.2f}", "-i", audio_bed(dur, a)]
    args += ["-filter_complex", fc, "-map", f"[{out_label}]"]
    if a.audio == "none":
        args += ["-an"]
    else:
        args += ["-map", "1:a", "-c:a", "aac", "-b:a", "96k", "-shortest"]
    args += ["-c:v", "libx264", "-crf", str(a.crf), "-preset", a.preset,
             "-pix_fmt", "yuv420p", "-movflags", "+faststart", os.path.abspath(a.output)]
    run(args, cwd=os.path.dirname(os.path.abspath(a.output)) or ".")
    print(f"✓ {a.output}   {w}×{h}  {dur:.2f}s  {a.grade}  噪点{a.noise}  扫描线{a.scanlines}")


def _csv(s):
    return [p.strip() for p in (s or "").split(",") if p.strip()]


def parse_times(s, n, default):
    out = []
    for p in _csv(s):
        m = re.match(r"^(\d{1,2}):(\d{1,2})$", p)
        if not m:
            sys.exit(f"--times 格式不对：{p}（应写成 20:07,22:40,09:15）")
        out.append((int(m.group(1)) % 24, int(m.group(2)) % 60))
    while len(out) < n:
        out.append(out[-1] if out else default)
    return out[:n]


def parse_days(s, n):
    out = []
    for p in _csv(s):
        try:
            out.append(int(p))
        except ValueError:
            sys.exit(f"--days 格式不对：{p}（应写成 0,0,0,0,3）")
    while len(out) < n:
        out.append(out[-1] if out else 0)
    return out[:n]


def parse_cams(s, n):
    out = []
    for p in _csv(s):
        no, _, name = p.partition(":")
        out.append((no.strip(), name.strip()))
    while len(out) < n:
        out.append(out[-1] if out else ("", ""))
    return out[:n]


def build_segments(a, durs):
    """默认：一个连续分段，时间戳一路走字。
    给了 --times 就按镜头逐段跳时（监控素材经常是同一台机器、几天后再看）。
    """
    n = len(durs)
    times = parse_times(getattr(a, "times", None), n, (a.hour, a.minute))
    days = parse_days(getattr(a, "days", None), n)
    cams = parse_cams(getattr(a, "cams", None), n)
    segs, acc = [], 0.0
    for d, (hh, mm), dy, (no, name) in zip(durs, times, days, cams):
        segs.append(seg(acc, acc + d, BASE_DATE + timedelta(days=dy, hours=hh, minutes=mm), no, name))
        acc += d
    return segs


def cmd_join(a):
    shots = a.inputs
    if not shots:
        sys.exit("没有输入片段")
    infos = [probe(s) for s in shots]
    first = next((i for i in infos if i.get("width")), infos[0])
    w, h = (parse_size(a.size) if a.size else (first.get("width", 1280), first.get("height", 720)))
    w, h = w - w % 2, h - h % 2
    durs = [i.get("duration") or 5.0 for i in infos]
    if a.each:
        durs = [min(d, a.each) for d in durs]
    body_total = sum(durs)

    n = len(shots)
    head, tail = a.head, a.tail
    head_dur = duration_of(head) if head else 0.0
    tail_dur = duration_of(tail) if tail else 0.0
    full_total = head_dur + body_total + tail_dur
    idx_head = n if head else None
    idx_tail = (n + (1 if head else 0)) if tail else None
    idx_audio = n + (1 if head else 0) + (1 if tail else 0)

    font = pick_font(a.font)
    outdir = os.path.dirname(os.path.abspath(a.output)) or "."
    os.makedirs(outdir, exist_ok=True)
    ass_name = "_osd_join.ass"
    # 时间戳只盖正片：片头/片尾卡不该有 OSD
    segments = build_segments(a, durs)
    build_ass(os.path.join(outdir, ass_name), w, h, segments, a, font)

    if a.fit == "crop":
        geo = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
    else:
        geo = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black"

    # 每段：归一化 → 裁时长
    fc = []
    for i, d in enumerate(durs):
        fc.append(f"[{i}:v]{geo},setsar=1,fps={a.fps},trim=duration={d:.3f},setpts=PTS-STARTPTS[n{i}]")
        if a.audio in ("keep", "mix"):
            if infos[i].get("audio"):
                fc.append(f"[{i}:a]atrim=duration={d:.3f},aresample=48000,asetpts=PTS-STARTPTS[a{i}]")
            else:
                fc.append(f"aevalsrc=0:d={d:.3f}:s=48000[a{i}]")
    for idx, label in ((idx_head, "hd"), (idx_tail, "tl")):
        if idx is not None:
            fc.append(f"[{idx}:v]{geo},setsar=1,fps={a.fps},setpts=PTS-STARTPTS[{label}]")

    if a.audio in ("keep", "mix"):
        fc.append("".join(f"[n{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[cat][aud0]")
        fc.append("[aud0]apad[aud]")
    else:
        fc.append("".join(f"[n{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[cat]")

    chain = look_chain(w, h, a)
    gsrc, gwin = glitch_tail(w, h, body_total, a)
    if gsrc:
        fc.append(f"[cat]{chain}[base]")
        fc.append(gsrc)
        fc.append(f"[base][gl]overlay=enable='{gwin}':shortest=1[vg]")
        pre = "vg"
    else:
        fc.append(f"[cat]{chain}[vg]")
        pre = "vg"
    fc.append(f"[{pre}]subtitles={ass_name}[vb]")

    # 片头 / 片尾接在 OSD 之外
    cur = "vb"
    if idx_head is not None:
        fc.append(f"[hd][{cur}]concat=n=2:v=1:a=0[vh]")
        cur = "vh"
    if idx_tail is not None:
        fc.append(f"[{cur}][tl]concat=n=2:v=1:a=0[vout]")
        cur = "vout"

    args = []
    for s in shots:
        args += ["-i", os.path.abspath(s)]
    for extra in (head, tail):
        if extra:
            args += ["-i", os.path.abspath(extra)]
    if a.audio != "none":
        args += ["-f", "lavfi", "-t", f"{full_total:.2f}", "-i", audio_bed(full_total, a)]
        if a.audio == "mix":
            fc.append(f"[aud][{idx_audio}:a]amix=inputs=2:duration=first:normalize=0[aout]")

    args += ["-filter_complex", ";".join(fc), "-map", f"[{cur}]", "-t", f"{full_total:.3f}"]
    if a.audio == "none":
        args += ["-an"]
    elif a.audio == "keep":
        args += ["-map", "[aud]", "-c:a", "aac", "-b:a", "128k"]
    elif a.audio == "mix":
        args += ["-map", "[aout]", "-c:a", "aac", "-b:a", "128k"]
    else:
        args += ["-map", f"{idx_audio}:a", "-c:a", "aac", "-b:a", "96k"]
    args += ["-c:v", "libx264", "-crf", str(a.crf), "-preset", a.preset,
             "-pix_fmt", "yuv420p", "-movflags", "+faststart", os.path.abspath(a.output)]
    run(args, cwd=outdir)
    extras = "".join(["  片头" if head else "", "  片尾" if tail else ""])
    print(f"✓ {a.output}   {n} 镜  {full_total:.2f}s  {w}×{h}  {a.grade}  音频 {a.audio}{extras}")


def cmd_still(a):
    info = {"width": 1280, "height": 720}
    try:
        p = subprocess.run([need_ffmpeg(), "-hide_banner", "-i", a.input], capture_output=True, text=True)
        m = re.search(r"(\d{2,5})x(\d{2,5})", p.stderr or "")
        if m:
            info = {"width": int(m.group(1)), "height": int(m.group(2))}
    except Exception:
        pass
    w, h = (parse_size(a.size) if a.size else (info["width"], info["height"]))
    w, h = w - w % 2, h - h % 2
    chain = look_chain(w, h, a, temporal=False)
    run(["-i", os.path.abspath(a.input), "-vf", chain, "-frames:v", "1", "-q:v", "2", os.path.abspath(a.output)])
    print(f"✓ {a.output}   {w}×{h}  {a.grade}")


def cmd_card(a):
    w, h = parse_size(a.size)
    font = pick_font(a.font)
    outdir = os.path.dirname(os.path.abspath(a.output)) or "."
    os.makedirs(outdir, exist_ok=True)
    ass_name = "_card.ass"
    size = max(20, int(round(min(w, h) * 0.052 * a.osd_scale)))
    small = max(14, int(round(min(w, h) * 0.028 * a.osd_scale)))
    head = ASS_HEADER.format(w=w, h=h, font=font, size=small, size2=small, size3=small, cardsize=size, pri="FFFFFF")
    ev = []
    lines = [x for x in (a.line1, a.line2, a.line3) if x]
    gap = size * 1.55
    y0 = h / 2 - gap * (len(lines) - 1) / 2
    for i, txt in enumerate(lines):
        fs = size if i == 0 else small
        y = y0 + gap * i
        fade = f"\\fad(260,120)\\fs{fs}"
        ev.append(f"Dialogue: 0,0:00:00.00,0:00:{a.duration:05.2f},CARD,,0,0,0,,{{\\pos({w / 2:.0f},{y:.0f}){fade}}}{txt}")
    with open(os.path.join(outdir, ass_name), "w", encoding="utf-8") as f:
        f.write(head + "\n".join(ev) + "\n")

    scan = ""
    if a.scanlines > 0:
        scan = f",drawgrid=w=iw:h={a.scanlines}:t=1:color=black@{a.scanline_alpha}"
    box = (
        f",drawbox=x=iw*0.11:y=ih*0.17:w=iw*0.78:h=ih*0.66:"
        f"color=white@0.10:t=1"
    )
    vf = f"noise=alls=8:allf=t,format=yuv420p,subtitles={ass_name}{scan}{box}"
    run(["-f", "lavfi", "-i", f"color=c=black:s={w}x{h}:r={a.fps}:d={a.duration}",
         "-vf", vf, "-c:v", "libx264", "-crf", str(a.crf), "-pix_fmt", "yuv420p",
         "-movflags", "+faststart", os.path.abspath(a.output)], cwd=outdir)
    print(f"✓ {a.output}   {a.duration}s 档案卡")


def cmd_sheet(a):
    d = duration_of(a.input)
    cells = a.cols * a.rows
    fps = max(cells / max(d, 0.1), 0.1)
    vf = f"fps={fps:.4f},scale={a.width}:-2:flags=lanczos,tile={a.cols}x{a.rows}"
    run(["-i", a.input, "-vf", vf, "-frames:v", "1", "-q:v", "3", a.output])
    print(f"✓ {a.output}   {a.cols}×{a.rows} 缩略图")


# ----------------------------------------------------------------------- CLI


def add_osd_args(p):
    g = p.add_argument_group("时间戳 / 机位")
    g.add_argument("--dynasty", default="大明", help="朝代，如 大明 / 大清 / 大唐")
    g.add_argument("--era", default="万历", help="年号，如 万历 / 乾隆 / 开元")
    g.add_argument("--year", type=int, default=15, help="年号第几年（数字）")
    g.add_argument("--ad-year", type=int, default=None, help="公元年，用于推干支（年号不在表里时用）")
    g.add_argument("--month", type=int, default=3, help="农历月")
    g.add_argument("--day", type=int, default=7, help="农历日")
    g.add_argument("--hour", type=int, default=14, help="起始钟点（24 小时制）")
    g.add_argument("--minute", type=int, default=32)
    g.add_argument("--clock-style", choices=["shichen", "modern"], default="shichen",
                   help="shichen=时辰刻分（默认）  modern=年号日期+现代时分秒")
    g.add_argument("--clock-speed", type=float, default=60.0, help="时钟倍速，默认 60（1 秒走 1 分）")
    g.add_argument("--cam", default="", help="机位名，如 御膳房·东廊")
    g.add_argument("--cam-no", default="", help="机位号，如 03")
    g.add_argument("--rec", action="store_true", default=True, help="闪烁红点（默认开）")
    g.add_argument("--no-rec", dest="rec", action="store_false")
    g.add_argument("--watermark", default="", help="左下角小字，如 内务府档案")
    g.add_argument("--osd-color", choices=list(OSD_COLORS), default="white")
    g.add_argument("--osd-scale", type=float, default=1.0, help="字号整体缩放")
    g.add_argument("--font", default=None, help="字体族名，默认自动挑中文字体")
    g.add_argument("--ganzhi", action="store_true", default=True, help="日期带干支")
    g.add_argument("--no-ganzhi", dest="ganzhi", action="store_false")


def add_look_args(p):
    g = p.add_argument_group("监控质感")
    g.add_argument("--grade", choices=list(GRADES), default="color", help="调色：color/gray/night/sepia")
    g.add_argument("--noise", type=int, default=14, help="噪点强度 0–40，默认 14")
    g.add_argument("--scanlines", type=int, default=4, help="扫描线间距像素，0=关，默认 4")
    g.add_argument("--scanline-alpha", type=float, default=0.075)
    g.add_argument("--vignette", type=float, default=4.2, help="暗角强度，PI/N，越大越轻，0=关")
    g.add_argument("--lowres", type=int, default=2, help="低清倍数，1=不降采样，默认 2")
    g.add_argument("--fps", type=int, default=25, help="掉帧到多少 fps，默认 25")
    g.add_argument("--glitch", action="store_true", help="插两处信号干扰雪花")
    g.add_argument("--fit", choices=["crop", "pad"], default="crop", help="比例不符时裁切还是加黑边")
    g.add_argument("--size", default=None, help="输出尺寸，如 1280x720")
    g.add_argument("--crf", type=int, default=20)
    g.add_argument("--preset", default="medium")
    g.add_argument("--audio", choices=["bed", "keep", "mix", "none"], default="bed",
                   help="bed=机房底噪（默认） keep=保留原声 mix=两者混 none=静音")
    g.add_argument("--bed-level", type=float, default=0.035, help="底噪音量 0–0.2")
    g.add_argument("--hum", type=float, default=0.006, help="50Hz 电流嗡鸣音量，0=关")


def main():
    ap = argparse.ArgumentParser(
        description="dynasty-cctv · 古代监控视频后期管线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--dry-run", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("probe", help="查看视频信息")
    p.add_argument("input")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("clock", help="年号/时辰换算")
    add_osd_args(p)

    p = sub.add_parser("osd", help="只生成时间戳字幕")
    add_osd_args(p)
    p.add_argument("-o", "--output")
    p.add_argument("-d", "--duration", type=float, default=20.0)
    p.add_argument("--size", default="1280x720")

    p = sub.add_parser("look", help="给单条片段套监控质感")
    p.add_argument("input")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--osd", action="store_true", help="同时烧时间戳")
    add_osd_args(p)
    add_look_args(p)

    p = sub.add_parser("join", help="多镜头拼接成片")
    p.add_argument("inputs", nargs="+")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--each", type=float, default=None, help="每段最多保留多少秒")
    p.add_argument("--times", default=None, help="逐镜起始时刻，逗号分隔：20:07,22:40,09:15")
    p.add_argument("--days", default=None, help="逐镜日期偏移（天），逗号分隔：0,0,0,0,3")
    p.add_argument("--cams", default=None, help="逐镜机位，逗号分隔：01:麦城·北门,04:麦城·粮仓")
    p.add_argument("--head", default=None, help="片头卡（不盖时间戳），如 head.mp4")
    p.add_argument("--tail", default=None, help="片尾档案卡（不盖时间戳），如 card.mp4")
    add_osd_args(p)
    add_look_args(p)

    p = sub.add_parser("still", help="静帧套质感")
    p.add_argument("input")
    p.add_argument("-o", "--output", required=True)
    add_look_args(p)

    p = sub.add_parser("card", help="片尾档案卡")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--line1", default="内务府档案")
    p.add_argument("--line2", default="")
    p.add_argument("--line3", default="")
    p.add_argument("-d", "--duration", type=float, default=1.6)
    p.add_argument("--size", default="1280x720")
    p.add_argument("--fps", type=int, default=25)
    p.add_argument("--scanlines", type=int, default=4)
    p.add_argument("--scanline-alpha", type=float, default=0.06)
    p.add_argument("--osd-scale", type=float, default=1.0)
    p.add_argument("--font", default=None)
    p.add_argument("--crf", type=int, default=20)

    p = sub.add_parser("sheet", help="抽帧拼图质检")
    p.add_argument("input")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--cols", type=int, default=3)
    p.add_argument("--rows", type=int, default=2)
    p.add_argument("--width", type=int, default=360)

    a = ap.parse_args()
    global DRY
    DRY = a.dry_run
    {
        "probe": cmd_probe,
        "clock": cmd_clock,
        "osd": cmd_osd,
        "look": cmd_look,
        "join": cmd_join,
        "still": cmd_still,
        "card": cmd_card,
        "sheet": cmd_sheet,
    }[a.cmd](a)


if __name__ == "__main__":
    main()
