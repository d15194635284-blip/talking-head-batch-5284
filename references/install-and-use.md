# 口播批剪 5284 安装与使用

## 在新聊天使用

本机已安装到用户 Skill 目录。新开聊天后输入下面的话，换成实际目录。

> 用 $talking-head-batch-5284 口播批剪 5284，处理 D:\新素材，成片输出到 D:\新成片。沿用大字包装、按语速变速和适度提亮。BGM 平均比人声低 6 分贝，片尾淡出 0.5 秒。先给两条样片。

确认整批时，把最后一句换成「直接处理整批并附删减与复核清单」。价格、地区、业务变化时给出顶部三行新文案。当前机器历史路径在根目录 local-settings.json，该文件属于本机配置。

## 给别人安装

将 ZIP 发给对方，解压后的 talking-head-batch-5284 文件夹放进 %USERPROFILE%\.codex\skills。最终为 %USERPROFILE%\.codex\skills\talking-head-batch-5284\SKILL.md。对方设置了 CODEX_HOME 时，使用该目录下的 skills。随后打开新聊天调用「口播批剪 5284」。

也可把 ZIP 交给 Codex 并说「安装包里的 talking-head-batch-5284，检查本地剪辑环境，按我提供的素材目录执行」。

依赖为 Python、FFmpeg（含 ffprobe 和 ass 滤镜）、本地 Whisper、OpenCV 与 NumPy。已有环境直接复用。需要安装时由 Codex 选择适合的 Python 环境。

```powershell
python -m pip install -r 路径/talking-head-batch-5284/requirements.txt
```

FFmpeg 单独安装并加入 PATH。初次准备 Whisper 需要下载模型，之后音频识别在本机运行。已有模型可复制到目标机器，默认缓存为 ~/.cache/whisper/small.pt。下面命令联网下载模型，prepare 自身要求模型已经就绪。

```powershell
python -c "import whisper; whisper.load_model('small')"
```

先让 Codex 执行 doctor 并验证一条样片。分享包包含参考包装与脚本，接收方提供自己的素材、本地配乐文件及中文字体。分享包不含 Whisper 模型或当前配乐音频。

## 运行时判断

默认效果适用于单个主讲人的竖版中文商业口播。每批由 Codex 阅读听写和画面后决定剪点、速度、字幕与提亮，用户不必手写计划。会议、多人轮流发言、原声嘈杂或句子不完整时保留有歧义的内容并记录复核项。

该 Skill 直接输出 MP4。局部脸部亮度通过 OpenCV 处理，幅度逐条判断。剪映可编辑工程和剪映原生美白参数需要另行接入对应工具。

本轮配乐与字幕可自由指定。请参考 [自定义配置](customization.md)。例如“配乐换成我的音乐，字幕用我提供的 SRT，字体改为微软雅黑 44 号，关闭顶部文案”。
