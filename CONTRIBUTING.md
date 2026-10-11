# 贡献与复现

需要 Python 3.10+，计算和测试不依赖第三方包。

```bash
python3 -m unittest discover -s tests -v
python3 skills/recalculate-grades/scripts/audit_grades.py examples/input.json --output /tmp/grade-audit-demo.json
```

修改计算口径时，先写一个能复现问题的虚构案例，再修改脚本。测试须断言可观察结果，例如总学分、最终综测、阻塞人员及退出码；不要只比对实现文本。

数据协议或报告字段变化时，同步修改 Skill 说明、references 和示例。预期输出应由人工核对的公式支持；重新生成文件本身不能证明计算正确。

提交 Issue/PR 时给出运行命令、Python 版本、预期与实际结果。使用 DEMO 学号、虚构课程和来源。不要上传真实成绩、截图、学号、个人信息或敏感日志。
