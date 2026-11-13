# 使用时更换配乐和字幕

每次调用用自然语言说明变更即可，Codex 负责把要求转成计划。当前默认文案与字体均可被本轮设置覆盖。每批单独保存计划，后续复查可以找到当时用的配乐和字幕样式。

## 配乐

顶层 music 可以是本地文件路径、配置对象或 null。单条 item.music 可覆盖整批值，null 表示该条无配乐。文件路径可以是绝对路径，或相对 plan.json 所在目录的路径。

配置对象支持 file、gap_db、fade_out。gap_db 默认 6，是音乐平均电平比剪后人声轨低的 dB 数，淡出前测量，数值越大音乐越轻。fade_out 默认 0.5 秒，0 表示关闭淡出。短音乐循环铺到视频结束。

命令行 --music 替换整批文件，--music-gap 调整整批音量差，--music-fade-out 调整整批淡出。单条 item.music 设置仍优先。--no-music 关闭所有条目的配乐。

本轮选择“沿用上次配乐”时，读取本机 local-settings.json 中已有文件路径。本轮指定其他音乐时使用新文件。只有用户要求更新默认时保存新默认。

## 口播字幕内容

默认使用 item.cues，每条为 [原片起始秒,原片结束秒,字幕文字]。用户提供字幕时，设置 item.subtitles，包含 file 和 timebase。

- file 指定 UTF-8 SRT 文件，支持相对 plan.json 的路径。
- timebase=source 表示字幕针对原素材，脚本按剪点和倍速同步。
- timebase=output 表示字幕已经对应成片，脚本直接使用成片时码。

同一条提供 subtitles 时会覆盖 cues。每条的 SRT 文件单独指定。修改字幕文件后指纹变化，重做时使用新 id 或 --rebuild。

用户提供纯文稿时，Codex 应结合本地逐词时间核对和对齐，再生成 cues。转写和字幕修订都要对照实际语音。

## 外观与固定文字

整批 style 是 assets/style.json 的部分覆盖；--style 也可指定一个 JSON 样式文件；单条 item.style 可单独覆盖整批。旧版 item.title_y、item.cta_y、item.caption_y 继续支持，并优先于同条 style 中的位置字段。

| 字段 | 示例与作用 |
| --- | --- |
| title | 三条字符串组成的数组，替换顶部固定文案 |
| cta | 替换评论引导文案 |
| show_title / show_cta / show_captions | true 或 false，分别控制三种文字 |
| font | 全部文字的默认字体家族，需本机已安装 |
| title_font / cta_font / caption_font | 对应文字组的独立字体 |
| title_size / cta_size / caption_size | ASS 字号，按 720×1280 画布计算 |
| title_color / cta_color / caption_color | #RRGGBB 格式的文字颜色 |
| title_outline_color / cta_outline_color / caption_outline_color | #RRGGBB 格式的描边颜色 |
| title_outline / cta_outline / caption_outline | 描边宽度，0–12 |
| title_y | 三行顶部纵坐标，默认 [75,137,199] |
| cta_y / caption_y | 评论引导和字幕顶部纵坐标，默认 855 / 950 |

参考 caption-style-example.json 和 custom-plan-example.json。字号、文案、字体变化后检查文字宽度、上下间距和遮脸情况。屏幕外文字不会自动缩小，Codex 需调整拆句、字号或位置并重新查看。

字幕颜色默认白色，顶部黄字黑边，评论引导红白。用户本轮明确要求其他颜色时按该要求处理。关闭某类文字时使用对应 show 开关。
