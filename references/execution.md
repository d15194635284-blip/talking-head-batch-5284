# 执行说明

PowerShell 命令示例，替换素材、输出和配乐路径。

```powershell
$clipSkill = "$env:USERPROFILE\.codex\skills\talking-head-batch-5284"
python "$clipSkill\scripts\pipeline.py" doctor
python "$clipSkill\scripts\pipeline.py" prepare --source 'D:\素材' --work 'D:\成片\.work-5284\prepare' --model small
python "$clipSkill\scripts\pipeline.py" render --plan 'D:\成片\.work-5284\plan.json' --output 'D:\成片' --work 'D:\成片\.work-5284\render' --music 'D:\配乐\统一BGM.mp3' --music-gap 6
```

prepare 使用 PATH 中的 whisper，可用 --whisper 指定完整程序路径，--model-dir 指定已有的本地模型目录。--prompt 提供业务专名，仍需核对原声。--limit 2 用于样片验证。视频只枚举素材目录当前层，按文件名排序。

prepare 每条目录包含 analysis.json、speech.json、speech.wav 和 contact.jpg。analysis.json 保存原片路径、哈希、音画信息与静音、冻结候选。原片哈希一致时复用准备结果。

## 计划字段

顶层对象包含 items 数组、可选的 style 包装覆盖与 music 配乐设置。示例见 plan-example.json。

| 字段 | 含义 |
| --- | --- |
| id | 本轮唯一名称，字母、数字、中文、连字符与下划线 |
| source | 当前机器原视频绝对路径 |
| keep | 递增保留区间，单位秒，例如 [[0.8,5.4],[5.7,10.2]] |
| cues | 原片时码字幕，每条为 [起始秒,结束秒,文字] |
| speed | 通常 1.00–1.25，逐条判断 |
| overall | 整体中间亮度增量，通常 0–0.025，可用 0–0.06 |
| face | 主讲脸部明度增量上限，通常 0–14，可用 0–20 |
| speaker_x | 主讲横向位置比例，默认 0.5，需看画面确认 |
| face_roi | 人脸检测的垂直范围比例，默认 [0.15,0.65] |
| title_y | 三行文字顶部坐标，默认 [75,137,199] |
| cta_y / caption_y | 评论引导和字幕顶部坐标，默认 855 / 950 |
| cut_notes | 本条剪点原因 |
| review | 需要复核的问题字符串数组，默认 [] |

坐标以 720×1280 为准。其他画幅会适配进竖版并留边，先判断用户希望的画幅。style.title 设置三行文案，style.font 设置已安装字体。文案或字体变化后检查宽度与排版。

render 先同步剪音画并以 30 fps 保持音高变速，再提亮，最后加入字幕和固定文案。字幕按剪点和倍速映射。被剪点拆开的同一句字幕需复核阅读时间。

配乐平均电平取与成片同长的开头区间，人声取剪后音轨平均电平，差值由 --music-gap 指定。默认 6，数值越大配乐越低。这是平均 dBFS 差值。最终混音有峰值限制器，片尾音乐淡出 0.5 秒。

## 恢复与验收

失败留在本轮处理结果中，重跑复用身份及文件哈希一致的成功成片。修改已有计划后重做可用 --rebuild。中间文件可重建，原素材保留。同一批按顺序运行，新批次使用独立工作目录。

脚本检查音画差小于 0.15 秒并完整解码，生成五帧联系表。Codex 仍需查看画面并核对剪点、字幕、人脸跟踪和配乐。仅通过解码时不能声称听审完成。识别不准、句子不完整、多人交错、遮挡或人脸跟踪不足写入 review。

配乐与字幕可在每次调用时更换，详见 [自定义配置](customization.md)。SRT 可按原片时间自动重排，也可直接使用成片时间。
