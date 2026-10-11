# Grade Audit Skill · 课程成绩重算与综测核对

[![Tests](https://github.com/W-sir0/grade-audit-skill/actions/workflows/tests.yml/badge.svg)](https://github.com/W-sir0/grade-audit-skill/actions/workflows/tests.yml)
![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A reusable AI skill with deterministic grade recalculation, credit validation and traceable audit reports.

把成绩表核对流程做成可复用的 AI Skill，并用确定性脚本计算和验证。适用于按指定名单筛选不及格人员、核查逐课学分、重算科学文化成绩和综合测评、核对缓考补录。

**规则可配置，计算可追溯，问题可定位。** 示例中的学校规则仅作演示；真实任务须先确认本校、本专业、本学期的计算口径。

## 能解决什么问题

- 挂科按 0 计分时仍保留课程学分，避免错用“已得学分”作为分母。
- 按字符串学号匹配和控制名单，保留前导零、同名人员及用户顺序。
- 明确区分正常、挂科、缓考、未出分和缺考；不把所有 0 分直接视为挂科。
- 校验课程清单、学分来源、等级换算和考试记录；缺失或冲突时阻止相关人员出分。
- 使用 Decimal，综测默认使用未提前取整的科学文化成绩；展示采用四舍五入两位。
- 保留逐课计算、规则快照、分子、分母和阻塞原因。

## 快速体验（无需 AI 环境）

Python 3.10+，无需安装第三方依赖。原始 Excel/PDF/照片先由助手或人工核验并转换为标准 JSON；本脚本不直接读取或写入 Excel。

```bash
cd grade-audit-skill
python3 skills/recalculate-grades/scripts/audit_grades.py examples/input.json --output /tmp/grade-audit-demo.json
python3 -m unittest discover -s tests -v
```

数据格式见 [数据与计算协议](skills/recalculate-grades/references/data-contract.md)。退出码 0 表示全部通过；2 表示存在阻塞或输入无效，必须检查报告；3 表示报告写入失败。写入失败时原报告不会被覆盖。无效输入会生成 `status=invalid` 的报告，避免旧报告被误认作新结果。输入和输出不可使用同一路径。

## 安装 Skill

需要支持 `SKILL.md` 的 AI 工作环境。Codex 用户可将本仓库的 Skill 文件夹复制到本地 Skills 目录：

```bash
git clone https://github.com/W-sir0/grade-audit-skill.git
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
cp -R grade-audit-skill/skills/recalculate-grades "${CODEX_HOME:-$HOME/.codex}/skills/"
```

安装后在新对话中选择或调用 `$recalculate-grades`。若已存在同名 Skill，先比较内容，避免覆盖自己的修改。

示例请求：

> 使用 $recalculate-grades，按我给的名单筛选本学期不及格人员。挂科按 0 分但学分计入分母，科学文化占 70%、考评占 30%。缓考未出分先列为待确认；只更新指定工作表，保留其他班级、顺序和排名。

提供本次成绩表、课程学分依据、指定名单和计算规则。名单可来自照片，模糊处仍需人工核验。

## 虚构示例

`examples/` 中的姓名、学号、班级、课程与来源均为虚构。

| 示例学号 | 计算方式 | 科学文化 | 考评 | 综测 |
|---|---|---:|---:|---:|
| DEMO-001 | 两门各 2 学分，59 分记 0，80 分正常计入 | 40.00 | 80 | 52.00 |
| DEMO-002 | 无挂科，按演示配置沿用原加权分 88.125 | 88.13 | 90 | 88.69 |

第二人的综测使用 88.125 计算。更多测试覆盖 59/60 边界、等级成绩、0 分歧义、缓考补录、重复姓名/学号、漏课、缺失学分、未取整计算和 CLI 失败退出码。

测试与贡献说明见 [CONTRIBUTING.md](CONTRIBUTING.md)。报告包含逐课来源、考评分来源及复用原加权分的依据。

## 项目结构

```text
skills/recalculate-grades/
  SKILL.md                  AI 工作流程与边界
  agents/openai.yaml        Skill 界面信息
  scripts/audit_grades.py   确定性计算与审计
  references/              数据协议、工作簿核验要求
examples/                  虚构输入与完整预期输出
tests/                     自动化测试
.github/workflows/         GitHub Actions
```

## 使用边界

本项目提供核对流程和计算工具，不代替学校政策或教务确认，不自动作出奖惩、录取等资格决定。当前计算核心支持单学期、0–100 分制、已核验的单次有效考试记录；跨学期应分别运行，其他分制或取整规则需修改并验证。

真实成绩文件、截图、学生信息、标准化输入、审计报告和日志请放在仓库外，或放进已忽略的 `private-data/`。不要添加到 Git，包括提交历史。仓库只接收代码、通用规则和明确虚构的案例；`.gitignore` 不能替代上传前检查。

MIT License。
