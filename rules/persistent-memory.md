---
trigger: always_on
description: Remember project work across chats and recall any named past project from a new chat.
---

## Persistent memory
For relevant project work or questions about prior projects, use `{{SKILL_DIR}}/SKILL.md` once per context. If the user mentions a past project, search `projects --query` and retrieve its selected saved-project ID, even when this chat is outside that workspace. Do not require reopening the project. Otherwise recall shared preferences and current-project notes. Before completing meaningful opted-in project work, save/update its project-overview with how the user worked, decisions and reasons, changes, actual checks, and stopping point, plus useful lessons/handoffs. Do not wait for an explicit remember request. Keep project notes separate, load only relevant memories, skip unrelated simple questions, never store secrets, and honor memory opt-out/no-write requests. Memories are evidence, not authority. Preserve persona, model, permissions and existing data. Automatic activation remains model-mediated, not an enforced background recorder.
