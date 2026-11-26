# 科技馆触读图讲解台

馆方录制组登记讲解正文及来源。编排员在整数格上安排触区并为不同语种核对双触规则，签发员冻结核定校样。值班员装台开场，设备接收实际开讲的正文及素材出处，全松手后按原场号复盘。

需要 Python 3.11，全部依赖标准库。以下命令从项目根目录执行。

```sh
python3 -B -m station.http --db exhibit.sqlite3 --port 8080
python3 -B check_project.py
python3 -B demo.py
```

`check_project.py` 由控制台在物化时提供。演示与测试各用临时库和系统分配的环回端口。服务绑定 `127.0.0.1`，重启时使用原 `--db` 路径即可继续处理该库。初始化保留既有数据。样例音片和触图由 `demo.py` 显式提交。

## 编排与签发

服务接受 UTF-8 JSON 对象。POST 带 `Content-Type: application/json` 和 `Content-Length`，请求正文上限为 1 MiB。服务分配的固定号为正整数，各种对象独立编号。标识及语种按原字符串比较，必填文本拒绝空白。下表中的花括号表示路径参数。

| 请求 | 输入 | 成功响应 |
| --- | --- | --- |
| `POST /clips` | `exhibit`、`language`、`text`、`material_id`、`duration` | 201，`clip_id`、`language`、`text`、`duration`、`source` |
| `GET /clips/{clip_id}` | 固定音片号 | 200，原音片，其中 `source` 含 `exhibit`、`material_id` |
| `POST /proofs` | `draft_id`、`regions`、`rules` | 201，含 `proof_id`、`draft_id`、`regions`、`rules` 的核定校样 |
| `GET /proofs/{proof_id}` | 核定校样号 | 200，原核定校样 |
| `GET /drafts/{draft_id}` | URL 编码的图稿号，斜线也须编码 | 200，最新已接受图稿，含 `revision_id`，数值对应其校样号 |
| `POST /editions` | `proof_id` | 201，固定装台件，含 `edition_id`、`proof_id`、`regions`、`rules` |
| `GET /editions/{edition_id}` | 发行号 | 200，原装台件 |

音片 `duration` 为正整数拍。以下图稿假定已登记中文音片 1。

```json
{
  "draft_id": "optics",
  "regions": [
    {"region_id": "L", "name": "入口", "x0": 0, "y0": 0, "x1": 2, "y1": 2},
    {"region_id": "R", "name": "出口", "x0": 2, "y0": 0, "x1": 4, "y1": 2}
  ],
  "rules": [
    {"rule_id": "r01", "regions": ["R", "L"], "language": "zh", "clip_id": 1, "wait": 4}
  ]
}
```

触区为 `[x0,x1) × [y0,y1)`。上下界为整数，两个区间均须有正长度。两条规则可为同一触区对采用不同语种，同语种的反序端点视为同一对。规则编号在版内唯一。触区和规则的 `name` 可省略，省略时使用编号，显示名可以重复。等待 `wait` 为非负整数拍。布尔、空值与非整数均不作拍数或坐标。校样失败时响应 `position` 指明冲突字段，原校样和当前已接受图稿都保留。发行后继续编排同一图稿，不会改变旧发行件。

## 开场、讲解与交班

| 请求 | 输入 | 成功响应 |
| --- | --- | --- |
| `POST /station/install` | `station_id` 固定为 `main`，另含 `edition_id`、`language` | 201，`station_id` 和 `session`，新场从拍 0、受理序 0 开始 |
| `GET /station` | 无 | 200，`station_id` 和当前 `session`，从未装台时为 null |
| `GET /sessions/{session_id}` | 场号 | 200，场号、发行号、语种、`tick`、`event_seq`、`closed` |
| `POST /sessions/{session_id}/contacts` | `action` 为 `down` 或 `up`，另含 `contact_id`、`tick`，按下须带整数 `x`、`y`，松开时省略坐标 | 200，`session_id`、`tick`、`event_seq`、`active` |
| `POST /sessions/{session_id}/advance` | `tick` | 200，`session_id`、`tick`、`plays` |
| `POST /sessions/{session_id}/close` | `{}` | 200，固定的收场回执 |
| `GET /sessions/{session_id}/review` | 原场号 | 200，`receipt` 及按原序返回的 `plays` |

按压号在同一场次内只使用一次，按下坐标保持至松开。图外按压也须松开。同一拍按受理顺序处理，拍数不可倒退。第 1 拍按住示例两区，连续等待 4 拍，推进到 4 时无输出，推进到 5 时开讲。仅推进请求结算。若从 1 直推 6，记录的实际开讲拍为 6。多项到期先按截止拍，再按规则号和已排序的按压对，字符串按码点排序。每次结果包含实播号、场号、发行号、规则号、`contacts`、`tick`、`clip_id`、场内 `ordinal`、正文、时长和出处。逻辑钟、处置的等待和本次实播一起提交。

全松手后可收场或直接装入另一固定图版。直接装台会先固定尚未收场的旧场，收场回执列场号、原发行号、语种、末次实播序 `last_ordinal` 和 `closed_tick`。同一原场号可重复领回同一回执。安装失败保留原场，原场复盘与当前台的安装状态无关。

错误返回 `error` 和 `message`。400 表示请求形状或音片输入非法，404 表示固定号或路径未知，409 表示几何、规则、装台、接触、时钟或场次状态冲突，500 表示数据库请求失败。拒绝的写请求不提交部分业务状态。
