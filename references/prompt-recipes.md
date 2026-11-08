# Prompt 配方

监控画面的 prompt 和普通文生图**方向相反**：普通 prompt 在加东西（光影、层次、氛围），监控 prompt 在**减东西**。你要的是一张"没有人认真拍过"的图。

## 一、首帧五段式（ImageGen 文生图）

```
[1 机位]  High corner security camera, wide-angle lens, 30° downward tilt, static fixed shot.
[2 场景]  朝代 + 地点 + 三件具体的东西（柱子/地面/器物）
[3 主体]  几个人 + 朝代服饰 + 一个定格动作（动作停在半途）
[4 光质]  Flat even lighting, no shadows, low dynamic range, slightly washed out.
[5 质感]  Grainy, soft focus, low resolution, security footage still, no text.
```

四个必须写死的词：

| 词 | 为什么 |
|---|---|
| `wide-angle lens` | 监控都是广角，人会被拉宽、边角会变形 |
| `30° downward tilt` | 机位在高处往下看，这个角度是这个形式的签名 |
| `flat even lighting` | 没有主光没有轮廓光，光从四面八方均匀来 |
| `no text, no timestamp, no watermark` | 不写这句，模型一定给你画一个糊掉的时间戳 |

**第五个词更关键，也最容易漏**：`No camera housing visible`。

写 `security camera mounted above a gate` 这种句子，模型会**把摄像头这个物体本身画进画面右上角**——它以为你要拍那个摄像头。要写"从这个机位看出去"，而不是"这里有个摄像头"：

| 别写 | 改写成 |
|---|---|
| `A security camera mounted above the gate` | `View from a high corner surveillance camera looking down at the gate` |
| `CCTV camera on the ceiling` | `View from the ceiling corner, wide angle, looking down` |

顺手再加两句压住"电影感"，这是第二个高频翻车点：

```
plain off-centre framing with empty space     ← 别让它构图，构图一漂亮就假
no light falloff, no torch glow, no deep shadows, low contrast, washed out
```

模型默认会给你一束戏剧性的火把光加一片深阴影，那是电影，不是监控。监控的光是"平"的，甚至"难看"的。

**动作要停在半途**：手刚掀开盖子、刚把东西塞进嘴、刚回头。定格的动作比完整的动作更有"被拍到"的感觉。

### 完整示例 1 · 明 · 御膳房夜巡（夜视）

```
High corner security camera, wide-angle lens, 30 degree downward tilt, static fixed shot.
A narrow Ming dynasty palace kitchen corridor at night: red lacquered pillars, grey brick
floor, stacked wooden food boxes on a side table, one dim paper lantern at the far end.
A young Chinese eunuch in a dark blue Ming round-collar robe and black gauze cap stands by
the food box, one hand lifting the lid, the other pinching a piece of pastry, caught
mid-motion. Flat even infrared illumination, no shadows, low dynamic range, washed out.
Grainy, soft focus, low resolution, monochrome green-grey night vision, security camera
footage still, 4:3. No text, no timestamp, no watermark, no logo.
```

### 完整示例 2 · 清 · 县衙大堂（彩色）

```
High corner security camera, wide-angle lens, 35 degree downward tilt, static fixed shot.
A Qing dynasty county court hall: dark wooden beams, a tall magistrate's desk with a red
cloth, a wooden plaque behind it, grey brick floor.
A magistrate in a dark blue Qing official robe and official hat sits behind the desk,
head drooping mid-nod, half asleep. A clerk in a plain grey robe stands beside him,
one hand reaching toward the wooden gavel. Two kneeling villagers in the foreground,
facing each other, confused.
Flat even daylight from the doorway, no shadows, low dynamic range.
Grainy, soft focus, low resolution, slightly desaturated colour, security footage still,
16:9. No text, no timestamp, no watermark, no logo.
```

### 完整示例 3 · 宋 · 市集布庄（黑白）

```
High corner security camera, wide-angle lens, 30 degree downward tilt, static fixed shot.
A Song dynasty market street: wooden shopfronts with fabric bolts hanging, a stone road,
woven baskets on the ground.
A thin man in a plain Song straight-robe leans toward a customer, one hand slipping into
the customer's wide sleeve. A neighbouring stall keeper on the right is already turning,
holding a wooden steelyard in his raised hand.
Overcast flat daylight, no shadows, low dynamic range.
Grainy, black and white, soft focus, low resolution, security footage still, 4:3.
No text, no timestamp, no watermark, no logo.
```

### 完整示例 4 · 城墙垛口（夜视，极高俯角）

```
High corner security camera mounted on a watchtower, wide-angle lens, 50 degree downward
tilt, static fixed shot.
The top of a Ming dynasty city wall at night: grey brick battlements, a wooden watch hut,
a small oil lamp on the ground.
Two soldiers in Ming lamellar armour and padded coats sit on the parapet, one breaking a
steamed bun in half and handing the larger piece to the other.
Flat infrared illumination, heavy grain, no shadows.
Monochrome green-grey night vision, low resolution, security footage still, 16:9.
No text, no timestamp, no watermark, no logo.
```

### 负向词（照抄）

```
cinematic, dramatic lighting, rim light, shallow depth of field, bokeh, lens flare,
professional photography, colour grading, text, watermark, subtitles, timestamp, logo,
modern clothing, glasses, wristwatch, zipper, sneakers, plastic, glass window,
motion blur, tilted frame, dutch angle, fisheye distortion
```

> `fisheye distortion` 要放进负向：广角已经够了，真鱼眼会让画面变成玩具。

## 二、视频 prompt 配方（VideoGen 图生视频）

图生视频只写**变化**。画面已经在图里了，重复描述会诱导模型重绘，第一帧就不再是你的图。

```
Static camera, no movement. [谁] [做了什么，一句一个动作]. [第二个人的反应].
Same framing, same lighting, same grainy low-quality look.
```

| 段 | 内容 | 例 |
|---|---|---|
| 锚 | 先钉死机位 | `Static camera, no movement.` |
| 主 | 主动者做一个动作 | `The young eunuch lifts the lid and eats a piece of pastry.` |
| 次 | 第二个人进入或反应 | `A supervisor walks in from the far end of the corridor.` |
| 收 | 状态停在某处 | `The eunuch freezes with full cheeks and stands straight.` |
| 锁 | 锁住画质 | `Same framing, same lighting, same grainy low-quality look.` |

**动作幅度三档**：

- **L1 微动**：只有呼吸、衣料、烛火晃。用在纯氛围镜。
- **L2 自然**（默认）：走两步、抬一次手、转一次头。90% 的镜头用这档。
- **L3 事件**：进出画面、递东西、摔一跤。只用在包袱那一镜，一镜最多一次。

超过 L3 就崩——脸会变、手会多、衣服会融。

### 视频负向词

```
camera movement, pan, zoom, dolly, handheld, cinematic lighting, shallow depth of field,
slow motion, text, watermark, subtitles, face morphing, identity change, extra fingers,
extra limbs, warping background, changing architecture
```

## 三、朝代服化道速查（防穿帮）

| 朝代 | 男装 | 女装 | 头 | 建筑 | 最常穿帮 |
|---|---|---|---|---|---|
| 秦/汉 | 深衣、直裾、佩剑 | 曲裾深衣 | 冠、巾帻 | 夯土高台、黑红配色、瓦当 | 椅子、桌椅、瓷器、玻璃 |
| 唐 | 圆领袍、幞头、革带、靴 | 高腰襦裙、披帛 | 幞头、高髻 | 朱柱白墙、宏大斗拱、鸱吻 | 椅子（唐人多坐床）、玻璃、砖墙 |
| 宋 | 直裰、襕衫、东坡巾 | 褙子、抹胸、罗裙 | 幞头、冠 | 青瓦白墙、素雅木构、格子窗 | 满清服饰、艳丽彩画、玻璃窗 |
| 明 | 圆领袍、曳撒、直身、网巾、乌纱帽 | 袄裙、比甲 | 乌纱帽、四方平定巾、䯼髻 | 红墙黄瓦绿琉璃、斗拱、汉白玉栏杆 | 辫子、马褂、瓜皮帽 |
| 清 | 长袍马褂、辫子、瓜皮帽、顶戴花翎 | 旗装、两把头、钿子 | 顶戴、钿子 | 黄琉璃、满文匾额、琉璃影壁 | 汉式宽袖、乌纱帽、束发 |

**器物白名单**：烛台、灯笼、油灯、陶碗、漆器、铜盆、木托盘、竹篮、布包袱、算盘、毛笔砚台。
**器物黑名单**：玻璃杯、塑料、纸杯、白瓷细碗（唐宋以后才有）、铁皮、螺丝、拉链、电线。

写 prompt 时**每样东西都点朝代**（`Ming round-collar robe`、`Song straight-robe`、`Qing official hat`），比只写 `ancient Chinese` 稳得多。

## 四、出图后必看四件事

用 Read 打开首帧，逐条对：

1. **服饰**：朝代对不对？有没有眼镜、手表、拉链、运动鞋？
2. **文字**：模型有没有偷偷画时间戳、匾额、招牌？有就重出（后期会被真时间戳盖住，很脏）。
3. **机位**：是不是高处俯视？有没有变成平视或低角度？有没有景深虚化？
4. **人数与位置**：几个人？谁在左谁在右？后面写视频 prompt 要按这个顺序。

## 五、修图而不是重出（省钱）

首帧 80% 的毛病能用 ImageGen 的图生图改，比重新抽卡便宜：

| 毛病 | 图生图指令 |
|---|---|
| 太清楚、有景深 | `make it look like a low-quality security camera frame, everything in focus, heavy grain, flat lighting` |
| 颜色太艳 | `desaturate heavily, remove warm cinematic colour, flat grey daylight` |
| 多了个现代物件 | `remove the wristwatch from the man's left wrist, keep everything else identical` |
| 机位太平 | `re-frame from a high corner, looking down at 30 degrees, wide angle` |

`input_fidelity` 调高（如 `high`）能保住构图和人物，只改质感。
