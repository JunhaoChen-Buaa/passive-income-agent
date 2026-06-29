# Contributing

感谢你愿意改进被动收益 Agent。

## 本地开发

1. 运行 `install_windows.bat` 安装依赖。
2. 运行 `start_windows.bat` 启动前后端。
3. 在浏览器打开 `http://127.0.0.1:5174/`。

## 提交前检查

后端测试：

```powershell
$env:PYTHONPATH='backend'
.\backend\.venv\Scripts\python.exe -m pytest backend\tests
```

前端构建：

```powershell
cd frontend
npm.cmd --cache ..\.npm-cache run build
```

## 产品边界

这个项目是长期指数投资纪律工具，不是投资顾问。贡献新功能时请保持这些边界：

- 不自动下单。
- 不推荐个股。
- 不承诺收益。
- AI 只解释规则结果，不直接决定金额。
- 缺失数据必须显式展示，不能静默补齐。

## Pull Request 建议

- 尽量保持改动聚焦。
- 涉及规则、回测、现金池或市场温度时，请补充测试。
- 涉及用户界面时，请说明用户路径和截图。
