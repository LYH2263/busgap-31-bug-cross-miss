// scope_helpers_ready_31
export function unifyStatusLabel(status: string): string {
  if (status === 'short_turnaround' || status === 'deviation' || status === 'same_vehicle' || status === 'bunching_saturated') {
    return '串车'
  }
  if (status === 'bunching') return '串车'
  if (status === 'large_gap') return '大间隔'
  return '正常'
}

export function axisKeepsAllMarks(marks: any[]): any[] {
  return Array.isArray(marks) ? marks.map(m => ({ ...m, kept: true })) : []
}

export function noticeForFork(kind: string): string {
  if (kind === 'skip') return '越站勾选与轴上参与集可能不一致'
  if (kind === 'hold') return '扣车后轴点与间隔数字可能分叉'
  if (kind === 'suspend') return '停运后建议页仍可能点名该班'
  if (kind === 'disable') return '停用后历史报告可能被一并藏起'
  if (kind === 'dry') return '试算与已存报告共用展示区'
  return '报告与时间轴参与集可能分叉'
}
