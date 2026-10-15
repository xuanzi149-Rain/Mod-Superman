# DeepSeek调用排查与恢复（2026-10-15）

## 当前结论

本地配置、网络和错误处理已修正，模型生成仍被上游故障阻塞，不能标记完整链路恢复。官方https://status.deepseek.com/在本轮检查时显示DeepSeek V4.1 Flash API及对话服务部分中断，处于排查中；https://deepseek.statuspage.io/旧页面仍显示正常，不能据此否认实际503。

前轮已验证/models鉴权200、配置模型存在、/user/balance可用标志true。DNS/TLS正常。供应商返回503并明确提示服务过于繁忙；这与密码或本地字段校验错误不同。此前关闭思考模式虽合理，但不是本次上游故障的解决办法。

## 本轮真实诊断

用户明确授权诊断调用，本轮按需要只做5次，不自动循环重试，不跨供应商发送数据。

| 请求 | 结果 |
|---|---|
| Flash直连SSE，固定最小JSON | 约281ms返回503 |
| Flash直连非流式，同一最小JSON | 约203ms返回503；上游类型service_unavailable_error，提示Service is too busy |
| Flash系统代理非流式，同一最小JSON | 约234ms返回200头，但75秒未完成 |
| Pro直连非流式，同一最小JSON | 约204ms返回200头，但75秒未完成；不能作为验证通过的备选 |
| Flash直连实际装备请求 | 约187ms返回200头、60秒首段正文、65秒总超时；未生成文件 |

前四份记录位于build/backend/model-diagnostics。业务复验记录：build/backend/delivery-verification/e787e38c-b59e-47af-a99f-e64f426689a0/verification.json。不同网络路径及请求的表现不同，但直连业务请求也能复现长等待，因此不能把所有超时归咎于本机代理。

没有取得最终生成结果，调用用量未知。并未因为用户允许多次测试而持续请求故障服务；没有擅自更换模型、供应商或密钥。

## 已落实修正

- 默认显式直连，避免httpx隐式继承Windows系统代理。需要代理时在服务端设DEEPSEEK_USE_SYSTEM_PROXY=1；不修改Windows系统设置。
- 保留thinking.type=disabled、JSON结构、业务校验、人工确认和65秒总等待门槛。
- 收到401/403、402、429、500、503后立即分别报告鉴权、余额、限额、上游内部错误、上游繁忙；不先等待错误正文。503向网站返回model_overloaded和503，明确输入、草稿可保留并手动填写。
- HTTP200正文若包含上游error对象，也按供应商错误分类，不再冒充模型JSON结构错误。
- 阶段诊断仍只保存状态和耗时，不保存密钥、鉴权头、模型正文或推理内容。
- verify_delivery失败时自动保存脱敏verification.json，而非只留下脚本断言输出。
- 新增diagnose_deepseek脚本，用固定最小JSON请求验证direct/system及流式/非流式；需明确授权后才执行，因为会实际调用模型并产生用量。

最终87项不联网检查通过，9.638秒；日志build/backend/deepseek-recovery-tests.log。包括503/402分类、HTTP200错误封装、代理显式配置，以及之前生成、确认、恢复与反馈回归。

## 恢复条件与后续

网站当前继续提供手动参数制作。一次API返回HTTP200或账户可用，都不等于模型生成恢复。

Flash服务恢复后，先做一条最小生成检查，成功再执行真实装备链路和代表性解析回归。当前没有安排后台定时复验，也没有承诺恢复时间。

如需立即恢复AI能力，需要另一个实际可用的模型服务；本轮Pro未通过，因此不自动切换。接入其他服务还需用户提供目标平台及在本地配置对应凭据，确认数据目的地和费用后再验证。

官方参考：[服务状态](https://status.deepseek.com/)、[503含义](https://api-docs.deepseek.com/quick_start/error_codes/)。
