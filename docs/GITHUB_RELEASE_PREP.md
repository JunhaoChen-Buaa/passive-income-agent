# GitHub 发布前准备

推荐仓库名：

```text
passive-income-agent
```

当前本机 Git 提交作者配置为：

```text
Junhao Chen <junhaochen@buaa.edu.cn>
```

GitHub 远程地址需要使用 GitHub 的精确账号名或组织名。注意：GitHub URL 中通常不是显示名，不能包含空格。

## 上传前请确认

- [ ] README 中产品定位、运行方式和免责声明准确。
- [ ] `.env`、`.deploy/`、`backend/data/`、`logs/`、`audit/` 没有被提交。
- [ ] `install_windows.bat` 可以安装依赖。
- [ ] `start_windows.bat` 可以启动应用。
- [ ] 后端测试通过。
- [ ] 前端构建通过。
- [ ] GitHub 仓库已经创建。
- [ ] 你确认 GitHub 账号和远程地址。

## 创建 GitHub 仓库后执行

在项目根目录运行：

```powershell
git remote add origin https://github.com/<your-github-account>/passive-income-agent.git
git branch -M main
git push -u origin main
```

如果你使用 SSH：

```powershell
git remote add origin git@github.com:<your-github-account>/passive-income-agent.git
git branch -M main
git push -u origin main
```

## 首个 Release 建议

Tag：

```text
v0.1.0
```

Release title：

```text
被动收益 Agent v0.1.0
```

Release notes：

```text
首个 MVP 版本：支持指数基金策略模板、AI 个人策略、真实历史 K 线回测、每日指数评估、行动指南、现金池和投资记录。

注意：本项目是长期指数投资纪律辅助工具，不自动下单，不承诺收益，不构成投资建议。
```
