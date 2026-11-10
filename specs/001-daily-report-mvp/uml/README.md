# UML 附件

PlantUML 源文件（`.puml`）与导出图（`.png`）一一对应，修改图必须改源文件后重新导出，不允许只改 PNG。

## 文件

| 源文件 | 导出 | 图类型 |
|---|---|---|
| `use-case.puml` | `use-case.png` | 用例图 |
| `data-flow.puml` | `data-flow.png` | 数据流图 |
| `class.puml` | `class.png` | 类图 |
| `er.puml` | `er.png` | ER 图 |
| `sequence-daily.puml` | `sequence-daily.png` | 关键序列图 |

`usecase-spec.md` 为用例清单、用例模板与关键用例详述。

## 重新导出

需要 Java 21 与 PlantUML（`D:\tools\plantuml\plantuml.jar`）：

```bash
cd specs/001-daily-report-mvp/uml
java -DPLANTUML_LIMIT_SIZE=8192 -jar D:/tools/plantuml/plantuml.jar \
  -tpng -charset UTF-8 -Sdpi=150 -Playout=elk class.puml
java -DPLANTUML_LIMIT_SIZE=8192 -jar D:/tools/plantuml/plantuml.jar \
  -tpng -charset UTF-8 -Sdpi=200 -Playout=elk data-flow.puml
java -DPLANTUML_LIMIT_SIZE=8192 -jar D:/tools/plantuml/plantuml.jar \
  -tpng -charset UTF-8 -Sdpi=200 -Playout=smetana use-case.puml er.puml
java -DPLANTUML_LIMIT_SIZE=8192 -jar D:/tools/plantuml/plantuml.jar \
  -tpng -charset UTF-8 -Sdpi=200 sequence-daily.puml
```

> 本机 Graphviz 不可用（`dot` 启动即崩溃），因此统一使用 PlantUML 内置布局（ELK / Smetana），不依赖外部 Graphviz。
