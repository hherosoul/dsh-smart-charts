import { fileURLToPath } from 'node:url'
import * as SkillFilesystem from '@deepseek-ai/dsh-skill-filesystem'

export const name = 'smart-charts-skills'

// 插件壳：仅负责把打包的 skills/ 目录注册进 ctx.skills。
// `ctx` 类型来自 Cordis；developer preview 阶段为避免硬编码类型包版本，
// 此处用 any（本文件是唯一入口，无业务逻辑）。
export function apply(ctx: any) {
  return ctx.plugin(SkillFilesystem, {
    providerName: 'smart-charts',
    includeDefaultRoots: false,
    customSkillDirs: [fileURLToPath(new URL('../skills/', import.meta.url))],
    watch: false,
  })
}
