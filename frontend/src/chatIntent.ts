// 聊天窗口里的"办事"意图识别：用轻量正则判断一句话是否想发起工单/报销，
// 命中后再调用后端 preview 接口做字段提取（无 LLM 调用，延迟很低）。
// 顺序上报销优先于工单，避免"帮我报销"被误判成工单。

export function shouldPreviewExpense(text: string): boolean {
  return /报销|报账|费用报销|申请费用|费用申请|报销费用|帮我报销|报销单/.test(text);
}

export function shouldPreviewTicket(text: string): boolean {
  if (shouldPreviewExpense(text)) return false;
  return /工单|帮我处理|帮忙处理|处理一下|处理这个|协助(我|一下|处理)?|找人(帮忙|处理|一下)?|反馈(问题|一下|bug)?|咨询(业务|一下)?|业务咨询|问问(业务|怎么)?|帮忙看看|麻烦处理/.test(
    text,
  );
}
