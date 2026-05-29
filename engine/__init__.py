# -*- coding: utf-8 -*-
"""
engine/ — 感知引擎包

包含视觉识别和通用工具模块：
  - engine.ocr          OCR 文字识别 + 车辆/UI 元素检测
  - engine.state_detect  基于颜色直方图 + OCR 的游戏状态检测器
  - engine.utils         日志、窗口操作、手柄按键等通用工具

向后兼容别名（允许旧代码中 `import module_ocr` 等写法通过 sys.path 继续工作）
已通过根目录的兼容存根 module_ocr.py / module_state_detect.py / utils.py 实现。
"""
