from __future__ import annotations

from .mysql_persona_source import PersonaMirrorSource


def build_demo_system_prompt(source: PersonaMirrorSource) -> str:
    agent_strategy = source.agent_strategy
    reply_tone = _string_value(agent_strategy.get("reply_tone"), fallback="自然、稳定、贴近目标用户风格")
    response_style = _string_value(agent_strategy.get("response_style"), fallback="结构清晰，贴近日常表达")
    preferred_length = _string_value(agent_strategy.get("preferred_length"), fallback="medium")
    empathy_first = bool(agent_strategy.get("empathy_first"))
    focus = _string_list(agent_strategy.get("focus"))
    avoid = _string_list(agent_strategy.get("avoid"))
    boundaries = _string_list(agent_strategy.get("boundaries"))

    sections = [
        "You are a demo chatbot that mirrors the public-text persona of a referenced Xiaohongshu user.",
        "You must not claim to be the real person, and you must not invent private facts or identity claims.",
        f"Mirror target nickname: {source.user_name}",
        f"Persona summary: {source.persona_summary}",
        f"Prompt profile: {source.prompt_profile}",
        "Behavior rules:",
        f"- Reply tone: {reply_tone}",
        f"- Response style: {response_style}",
        f"- Preferred length: {preferred_length}",
        f"- Empathy first: {'yes' if empathy_first else 'no'}",
    ]
    if focus:
        sections.append(f"- Focus on: {'; '.join(focus)}")
    if avoid:
        sections.append(f"- Avoid: {'; '.join(avoid)}")
    if boundaries:
        sections.append(f"- Boundaries: {'; '.join(boundaries)}")
    sections.extend(
        [
            "- Keep the reply style natural and conversational instead of sounding like a label report.",
            "- If the user asks about your identity, clarify that this is a mirrored style demo based on public text signals.",
            "- If the user asks for unsafe, illegal, or privacy-invasive help, refuse briefly and redirect.",
        ]
    )
    return "\n".join(sections)


def format_demo_chat_banner(source: PersonaMirrorSource) -> str:
    agent_strategy = source.agent_strategy
    reply_tone = _string_value(agent_strategy.get("reply_tone"), fallback="-")
    response_style = _string_value(agent_strategy.get("response_style"), fallback="-")
    llm_model = source.llm_model or "rule-based"
    confidence = source.confidence.get("overall", "-")
    return "\n".join(
        [
            f"demo mirror user: {source.user_name} ({source.source_user_id})",
            f"generation_mode: {source.generation_mode}",
            f"model_name: {llm_model}",
            f"reply_tone: {reply_tone}",
            f"response_style: {response_style}",
            f"confidence_overall: {confidence}",
            "Type /help for commands.",
        ]
    )


def _string_value(value: object, *, fallback: str) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else fallback


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
    return result
