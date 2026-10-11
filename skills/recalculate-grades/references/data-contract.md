# 数据与计算协议（v1）

计算核心只接受 UTF-8 JSON，依赖 Python 3.10+ 标准库。Excel、PDF、照片由执行 Skill 的助手先提取核验；脚本不做 OCR，不推测学分，不自动编辑工作簿。

## 顶层

| 字段 | 含义 |
|---|---|
| schema_version | 固定为数字 1 |
| term | 已确认的单一学期；跨学期任务分别运行 |
| roster | 目标学号字符串列表，顺序即输出顺序 |
| rules | 本次任务确认的规则（见下表） |
| students | 人员记录，学号必须与 roster 完全一致 |

## rules

| 字段 | 含义 |
|---|---|
| rule_source | 学校规则、用户确认或任务说明的来源定位 |
| pass_threshold | 及格线，例如字符串 "60" |
| grade_map | 等级到数值的字典，例如 {"优秀":"95","良好":"85","中等":"75","及格":"65"} |
| academic_weight / assessment_weight | 0 到 1，和必须为 1，例如 "0.7" / "0.3" |
| nonfailure_mode | recalculate 逐课重算；original 无挂科时使用原加权分 |
| zero_is_failure | 布尔值；false 时 normal 状态的 0 分待核验，显式 failed 的 0 分可计算 |
| unresolved | deferred、pending、absent 三个键，每个取 block / exclude / zero |

未确认的未出分处理设为 block。exclude 不进入分子和分母；zero 以 0 分进入分子，学分进入分母。zero 策略不会把未出分人员自动标记为已确认挂科。original 模式遇到任何未出分课均阻塞，防止复用口径不明的平均分。等级分按换算后的数值与及格线比较；学校另有等级及格规则时先调整配置。

## students 元素

| 字段 | 含义 |
|---|---|
| student_id / name / class_name | 学号、姓名、班级，非空字符串 |
| assessment / assessment_source | 考评分及来源定位 |
| expected_course_ids / course_list_source | 独立核验的应有课程 ID 列表及清单来源 |
| original_average / original_average_source | 仅复用原加权分时必填 |
| courses | 逐课记录列表 |

应有课程列表须来自该学生真实选课/成绩清单并核对培养方案，不能只从当前已提取记录复制生成，否则无法发现漏课。

## courses 元素

| 字段 | 含义 |
|---|---|
| course_id / name | 经别名核验后的稳定课程 ID 和课程名 |
| credits / credit_source | 正数学分和学分依据（文件/页/行或已确认教务记录） |
| status | normal、failed、deferred、pending、absent |
| score / score_source | 原始数值/等级和来源；后三种状态 score 必须为 null 或空字符串 |
| exam_record_id（可选） | 有效考试记录编号，保留用于溯源 |

所有 courses 均为本次已确认的计分课程范围；不计分课程在标准化阶段按有依据的规则排除，并保留单独的排除清单，不能临时丢弃低分课程。学分必须验证，包括 exclude 策略下的课程。

normal：非零且小于及格线即挂科记 0；等于及格线视为通过。failed：分数必须低于及格线，否则报冲突。pending/deferred/absent 若已出分，要核验考试记录后改为 normal 或 failed，再补录分数，不允许保留旧状态携带新成绩。

同名学生、同名课程允许有不同 ID。重复学号、重复课程 ID 或未决多次考试不能简单去重。脚本要求每名学生每个课程 ID 只有一个已选定考试记录。

数值建议全部用十进制字符串，学号始终为字符串。成绩限制 0–100；学分大于 0、不超过 1000；最多 16 位有效数字、10 位小数。Python 调用不接受二进制 float，CLI 将 JSON 小数解析为 Decimal。默认 Decimal 精度 60，仅展示字段按 ROUND_HALF_UP 保留两位；分子和分母保留供复核，循环小数的 unrounded 字段是高精度十进制近似值。

## 报告

全局范围/规则错误返回 status=invalid、errors 和空 results；课程或人员错误返回 status=blocked，仅受影响人员没有计算结果。其余人员仍可核验。failed_student_ids 只包含 status=ok 且至少一门已确认挂科课程的人员；blocked_student_ids 必须另行报告，不能视为通过。

每人输出课程原始字段、normalized_score、decision、counted_score、included_credits、weighted_points，以及总分子、总学分、精确计算值和两位显示值。original 模式仍输出逐课核验值，但 academic_unrounded 来自原表。报告包含 rules 快照，必须同时保存标准化输入，才能完整重现考评分、名单及来源。审计文件也含敏感成绩，不上传项目仓库。
