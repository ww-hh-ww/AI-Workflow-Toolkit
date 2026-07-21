import path from "node:path"

const sessionAgents = new Map()
const sessionAssignments = new Map()
const pendingAssignments = new Map()
let pythonCommand = []
let controlRoot = ""

async function resolveControlRoot(start) {
  const git = Bun.spawn(["git", "rev-parse", "--git-common-dir"], {
    cwd: start,
    stdout: "pipe",
    stderr: "pipe",
  })
  const commonText = (await new Response(git.stdout).text()).trim()
  if ((await git.exited) === 0 && commonText) {
    const common = path.isAbsolute(commonText) ? commonText : path.resolve(start, commonText)
    const candidate = path.dirname(common)
    if (await Bun.file(path.join(candidate, ".aiwf/state/state.json")).exists()) return candidate
  }
  let candidate = path.resolve(start)
  while (true) {
    if (await Bun.file(path.join(candidate, ".aiwf/state/state.json")).exists()) return candidate
    const parent = path.dirname(candidate)
    if (parent === candidate) return path.resolve(start)
    candidate = parent
  }
}

async function loadPythonCommand(root) {
  try {
    const config = await Bun.file(
      path.join(root, ".aiwf/runtime/internal/python-command.json"),
    ).json()
    if (Array.isArray(config.argv) && config.argv.length) return config.argv.map(String)
  } catch {}
  return globalThis.process.platform === "win32" ? ["py", "-3"] : ["python3"]
}

const toolNames = {
  read: "Read",
  glob: "Glob",
  grep: "Grep",
  list: "List",
  write: "Write",
  edit: "Edit",
  apply_patch: "MultiEdit",
  bash: "Bash",
  task: "Task",
  skill: "Skill",
}

function normalizeArgs(tool, args) {
  const result = { ...(args || {}) }
  if (!result.file_path && result.filePath) result.file_path = result.filePath
  if (tool === "skill" && !result.skill) result.skill = result.name || ""
  if (tool === "task" && !result.subagent_type) {
    result.subagent_type = result.agent || result.agentName || ""
  }
  return result
}

function applyUpdatedArgs(target, updated) {
  const value = { ...(updated || {}) }
  if (target.filePath !== undefined && value.file_path !== undefined) {
    value.filePath = value.file_path
    delete value.file_path
  }
  Object.assign(target, value)
}

function payload(eventName, input, args, response, cwd, agentType = "") {
  return {
    hook_event_name: eventName,
    session_id: input.sessionID || input.sessionId || "",
    cwd,
    tool_name: toolNames[input.tool] || input.tool || "",
    tool_input: normalizeArgs(input.tool, args),
    tool_response: response || null,
    agent_type: agentType,
  }
}

async function runHook(script, body, extraArgs = []) {
  const process = Bun.spawn([...pythonCommand, `${controlRoot}/scripts/${script}`, ...extraArgs], {
    cwd: controlRoot,
    env: { ...globalThis.process.env, AIWF_HOOK_ENGINE: "opencode" },
    stdin: new Blob([JSON.stringify(body)]),
    stdout: "pipe",
    stderr: "pipe",
  })
  const [stdout, stderr, exitCode] = await Promise.all([
    new Response(process.stdout).text(),
    new Response(process.stderr).text(),
    process.exited,
  ])
  if (exitCode === 2) throw new Error((stderr || stdout || "AIWF blocked this action").trim())
  if (!stdout.trim()) return null
  try {
    const result = JSON.parse(stdout)
    const specific = result.hookSpecificOutput || {}
    if (specific.permissionDecision === "deny" || result.decision === "block") {
      throw new Error(specific.permissionDecisionReason || result.reason || "AIWF blocked this action")
    }
    return result
  } catch (error) {
    if (error instanceof SyntaxError) return null
    throw error
  }
}

function patchPaths(patch) {
  const paths = []
  const pattern = /^\*\*\* (?:(?:Add|Update|Delete) File|Move to): (.+)$/gm
  for (const match of String(patch || "").matchAll(pattern)) paths.push(match[1].trim())
  return paths
}

async function sessionAgent(client, input) {
  const sessionID = input.sessionID || input.sessionId || ""
  if (!sessionID) return ""
  const cached = sessionAgents.get(sessionID)
  if (cached) return cached
  try {
    const response = await client.session.messages({ path: { id: sessionID } })
    const messages = response?.data || response || []
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      const info = messages[index]?.info
      if (info?.role === "assistant" && info.agent) {
        sessionAgents.set(sessionID, info.agent)
        return info.agent
      }
    }
  } catch {}
  return ""
}

async function prepareTaskRole(input, args) {
  const role = String(args.subagent_type || "")
  if (!["aiwf-executor", "aiwf-tester", "aiwf-reviewer"].includes(role)) return null
  if (args.background === true) {
    throw new Error(
      `AIWF ${role} must run in the foreground so its record is checked before the next Task role.`
    )
  }
  let ledger
  try {
    ledger = await Bun.file(`${controlRoot}/.aiwf/state/tasks.json`).json()
  } catch {
    return null
  }
  const prompt = [args.prompt, args.description].filter(Boolean).join("\n")
  const matches = (ledger.tasks || []).filter((task) => {
    if (task.status !== "active" || !task.id) return false
    return new RegExp(`(^|[^A-Za-z0-9_-])${task.id}([^A-Za-z0-9_-]|$)`).test(prompt)
  })
  if (matches.length !== 1) return null
  const assigned = matches[0].worktree_path
  if (!assigned) return null
  return { taskID: matches[0].id, role, worktree: path.resolve(assigned) }
}

function sessionID(input) {
  return input.sessionID || input.sessionId || ""
}

function assignedCwd(input, fallback) {
  return sessionAssignments.get(sessionID(input))?.worktree || fallback
}

function routePatchText(patch, assignment) {
  if (!assignment) return String(patch || "")
  return String(patch || "").replace(
    /^(\*\*\* (?:(?:Add|Update|Delete) File|Move to): )(.+)$/gm,
    (_line, prefix, rawPath) => {
      const value = String(rawPath).trim()
      if (path.isAbsolute(value)) return `${prefix}${value}`
      const normalized = value.startsWith("./") ? value.slice(2) : value
      const root = normalized === ".aiwf" || normalized.startsWith(".aiwf/")
        ? controlRoot
        : assignment.worktree
      return `${prefix}${path.resolve(root, normalized)}`
    },
  )
}

export const AIWFPlugin = async ({ client, directory, worktree }) => {
  // `directory` is the session cwd. In a non-Git project OpenCode may report
  // `/` as the worktree, which must not replace the real project directory.
  const cwd = directory || worktree
  controlRoot = await resolveControlRoot(cwd)
  pythonCommand = await loadPythonCommand(controlRoot)
  return {
    event: async ({ event }) => {
      if (event.type === "session.created") {
        const info = event.properties?.info
        const assignment = pendingAssignments.get(info?.parentID || "")
        if (info?.id && assignment) sessionAssignments.set(info.id, assignment)
        return
      }
      if (event.type === "session.deleted") {
        const info = event.properties?.info
        if (info?.id) sessionAssignments.delete(info.id)
        return
      }
      if (event.type === "message.updated") {
        const info = event.properties?.info
        if (info?.role === "assistant" && info.sessionID && info.agent) {
          sessionAgents.set(info.sessionID, info.agent)
        }
      }
    },

    "chat.message": async (input, output) => {
      if (input.agent) sessionAgents.set(input.sessionID, input.agent)
      const result = await runHook(
        "aiwf_status.py",
        payload("UserPromptSubmit", input, {}, null, cwd, input.agent || ""),
        ["--short"],
      )
      const note = result?.hookSpecificOutput?.additionalContext
      if (!note) return
      const textPart = output.parts.find((part) => part?.type === "text")
      if (textPart) textPart.text += `\n\n<system-reminder>${note}</system-reminder>`
    },

    "shell.env": async (_input, output) => {
      output.env.AIWF_HOST = "opencode"
      output.env.AIWF_HOOK_ENGINE = "opencode"
    },

    "tool.execute.before": async (input, output) => {
      const tool = input.tool
      const agentType = await sessionAgent(client, input)
      const hookCwd = assignedCwd(input, cwd)
      const assignment = sessionAssignments.get(sessionID(input))
      if (tool === "apply_patch") {
        const key = output.args.patchText !== undefined ? "patchText" : "patch"
        output.args[key] = routePatchText(output.args[key], assignment)
        for (const filePath of patchPaths(output.args[key])) {
          await runHook("aiwf_scope_check.py", payload(
            "PreToolUse", input, { file_path: filePath }, null, hookCwd, agentType,
          ))
        }
        return
      }

      const script = {
        read: "aiwf_worktree_route.py",
        glob: "aiwf_worktree_route.py",
        grep: "aiwf_worktree_route.py",
        list: "aiwf_worktree_route.py",
        write: "aiwf_scope_check.py",
        edit: "aiwf_scope_check.py",
        bash: "aiwf_bash_guard.py",
        task: "aiwf_agent_gate.py",
      }[tool]
      if (!script) return
      const taskRole = tool === "task"
        ? await prepareTaskRole(input, normalizeArgs(tool, output.args))
        : null
      const result = await runHook(
        script, payload("PreToolUse", input, output.args, null, hookCwd, agentType),
      )
      const updated = result?.hookSpecificOutput?.updatedInput
      if (updated) applyUpdatedArgs(output.args, updated)
      if (taskRole) pendingAssignments.set(sessionID(input), taskRole)
    },

    "tool.execute.after": async (input, output) => {
      const tool = input.tool
      const agentType = await sessionAgent(client, input)
      if (tool === "skill") {
        await runHook(
          "aiwf_skill_log.py", payload("PostToolUse", input, input.args, output, cwd, agentType),
        )
      } else if (tool === "task") {
        const childID = output.metadata?.sessionId || output.metadata?.sessionID || ""
        const assignment = pendingAssignments.get(sessionID(input))
        if (childID && assignment) sessionAssignments.set(childID, assignment)
        pendingAssignments.delete(sessionID(input))
        const result = await runHook(
          "aiwf_agent_log.py", payload("PostToolUse", input, input.args, output, cwd, agentType),
        )
        const note = result?.hookSpecificOutput?.additionalContext || result?.systemMessage
        if (note && typeof output.output === "string") {
          output.output += `\n\n${note}`
          if (childID) output.output += `\n\n[AIWF] OpenCode child task_id: ${childID}`
        }
      } else if (["write", "edit", "apply_patch"].includes(tool)) {
        const args = input.args || {}
        if (tool === "apply_patch") {
          for (const filePath of patchPaths(args.patchText || args.patch)) {
            await runHook("aiwf_auto_sync.py", payload(
              "PostToolUse", input, { file_path: filePath }, output, cwd, agentType,
            ))
          }
        } else {
          await runHook(
            "aiwf_auto_sync.py", payload("PostToolUse", input, args, output, cwd, agentType),
          )
        }
      }
    },

    "experimental.session.compacting": async (_input, output) => {
      const process = Bun.spawn([...pythonCommand, "-m", "aiwf_core.cli", "status", "--prompt"], {
        cwd: controlRoot,
        env: { ...globalThis.process.env },
        stdout: "pipe",
        stderr: "pipe",
      })
      const text = await new Response(process.stdout).text()
      await process.exited
      if (text.trim()) output.context.push(`\n## AIWF routing\n${text.trim()}\n`)
    },
  }
}
