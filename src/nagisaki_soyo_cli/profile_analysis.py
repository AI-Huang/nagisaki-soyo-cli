from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from .config import DEFAULT_MODEL, DEFAULT_TEMPERATURE, OPENAI_API_KEY, OPENAI_BASE_URL, PROFILE_RUNS_DIR
from .profile_prompts import PROFILE_SYSTEM_PROMPT

SOFTENERS = ("吧", "呢", "呀", "啦", "嘛", "哦", "诶")
POLITE_MARKERS = ("请", "谢谢", "麻烦", "辛苦", "拜托")
HEDGES = ("可能", "也许", "有点", "好像", "感觉", "大概", "似乎")
POSITIVE_WORDS = ("开心", "喜欢", "高兴", "放心", "期待", "谢谢", "幸福", "治愈")
NEGATIVE_WORDS = ("难过", "焦虑", "烦", "委屈", "生气", "害怕", "压力", "累")
EMPATHY_WORDS = ("抱抱", "辛苦", "加油", "别怕", "别担心", "没事", "理解")
LOGIC_WORDS = ("因为", "所以", "如果", "但是", "不过", "其实", "然后")
TOPIC_KEYWORDS = {
    "情感": ("喜欢", "想念", "关系", "分手", "恋爱", "心动"),
    "穿搭": ("穿搭", "衣服", "裙子", "外套", "鞋子", "包包"),
    "美妆": ("口红", "粉底", "妆容", "护肤", "面膜", "香水"),
    "消费": ("买", "下单", "价格", "便宜", "值得", "购物"),
    "学习": ("学习", "复习", "考试", "上课", "笔记", "作业"),
    "生活记录": ("今天", "最近", "日常", "周末", "吃饭", "散步"),
    "社交关系": ("朋友", "同事", "家人", "聊天", "见面", "联系"),
}


@dataclass
class TextSample:
    text: str
    source: str = "unknown"
    created_at: str | None = None


@dataclass
class AnalysisResult:
    user_name: str
    sample_count: int
    source_summary: dict[str, int]
    feature_summary: dict[str, Any]
    user_profile_facts: dict[str, Any]
    persona_summary: str
    agent_strategy: dict[str, Any]
    prompt_profile: str
    confidence: dict[str, float]
    evidence: dict[str, list[str]]
    generation_mode: str
    model_name: str | None
    generated_at: str


@dataclass
class ModelComparisonResult:
    compared_models: list[str]
    user_name: str
    sample_count: int
    results: list[AnalysisResult]
    generated_at: str


def load_text_samples(path: Path) -> list[TextSample]:
    if path.suffix == ".jsonl":
        return _load_jsonl_samples(path)
    if path.suffix == ".json":
        return _load_json_samples(path)
    if path.suffix == ".txt":
        return _load_txt_samples(path)
    raise RuntimeError(f"Unsupported input format: {path.suffix}")


def analyze_user_language(
    user_name: str,
    samples: list[TextSample],
    *,
    use_llm: bool,
    model: str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
) -> AnalysisResult:
    cleaned_samples = [TextSample(text=_clean_text(sample.text), source=sample.source, created_at=sample.created_at) for sample in samples]
    cleaned_samples = [sample for sample in cleaned_samples if sample.text]
    if not cleaned_samples:
        raise RuntimeError("No usable text samples were found after cleaning.")

    feature_summary = _compute_feature_summary(cleaned_samples)
    user_profile_facts = _build_user_profile_facts(feature_summary)
    rule_agent_strategy = _build_agent_strategy(user_profile_facts)
    rule_evidence = _build_evidence(cleaned_samples, feature_summary, user_profile_facts)
    rule_confidence = _build_confidence(feature_summary, used_llm=False)
    llm_bundle: dict[str, Any] | None = None
    if use_llm:
        llm_bundle = _build_llm_profile_bundle(
            user_name,
            user_profile_facts,
            feature_summary,
            cleaned_samples,
            fallback_confidence=rule_confidence,
            fallback_evidence=rule_evidence,
            model=model,
            temperature=temperature,
        )
    persona_summary = llm_bundle["persona_summary"] if llm_bundle else _build_persona_summary(user_name, user_profile_facts)
    agent_strategy = llm_bundle["agent_strategy"] if llm_bundle else rule_agent_strategy
    prompt_profile = llm_bundle["prompt_profile"] if llm_bundle else _build_prompt_profile(user_name, user_profile_facts, agent_strategy)
    confidence = llm_bundle["confidence"] if llm_bundle else rule_confidence
    evidence = llm_bundle["evidence"] if llm_bundle else rule_evidence
    source_summary = dict(sorted(Counter(sample.source for sample in cleaned_samples).items()))

    return AnalysisResult(
        user_name=user_name,
        sample_count=len(cleaned_samples),
        source_summary=source_summary,
        feature_summary=feature_summary,
        user_profile_facts=user_profile_facts,
        persona_summary=persona_summary,
        agent_strategy=agent_strategy,
        prompt_profile=prompt_profile,
        confidence=confidence,
        evidence=evidence,
        generation_mode="llm" if use_llm else "rule",
        model_name=model if use_llm else None,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def compare_user_language_models(
    user_name: str,
    samples: list[TextSample],
    *,
    models: list[str],
    temperature: float = DEFAULT_TEMPERATURE,
) -> ModelComparisonResult:
    compared_models = [model.strip() for model in models if model.strip()]
    if not compared_models:
        raise RuntimeError("At least one model is required for comparison.")
    results = [
        analyze_user_language(
            user_name=user_name,
            samples=samples,
            use_llm=True,
            model=model_name,
            temperature=temperature,
        )
        for model_name in compared_models
    ]
    return ModelComparisonResult(
        compared_models=compared_models,
        user_name=user_name,
        sample_count=results[0].sample_count if results else 0,
        results=results,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def save_analysis_result(result: AnalysisResult, output_path: Path | None = None) -> Path:
    path = output_path or _default_output_path(result.user_name)
    payload = asdict(result)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def save_model_comparison(result: ModelComparisonResult, output_path: Path | None = None) -> Path:
    path = output_path or _default_comparison_output_path(result.user_name)
    payload = asdict(result)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def format_analysis_summary(result: AnalysisResult) -> str:
    lines = [
        f"user_name: {result.user_name}",
        f"sample_count: {result.sample_count}",
        f"generation_mode: {result.generation_mode}",
        f"model_name: {result.model_name or 'rule-based'}",
        f"speaking_style: {', '.join(result.user_profile_facts['language_style'])}",
        f"tone: {', '.join(result.user_profile_facts['tone'])}",
        f"emotion_pattern: {', '.join(result.user_profile_facts['emotion_pattern'])}",
        f"common_topics: {', '.join(result.user_profile_facts['common_topics']) or 'none'}",
        f"agent_reply_tone: {result.agent_strategy['reply_tone']}",
        f"confidence_overall: {result.confidence['overall']:.2f}",
    ]
    return "\n".join(lines)


def format_model_comparison_summary(result: ModelComparisonResult) -> str:
    lines = [
        f"user_name: {result.user_name}",
        f"sample_count: {result.sample_count}",
        "model_results:",
    ]
    for item in result.results:
        lines.append(
            f"- {item.model_name or 'rule-based'} | confidence={item.confidence['overall']:.2f} | reply_tone={item.agent_strategy['reply_tone']}"
        )
    return "\n".join(lines)


def _load_json_samples(path: Path) -> list[TextSample]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [_coerce_sample(item) for item in payload]
    if isinstance(payload, dict):
        if "texts" in payload and isinstance(payload["texts"], list):
            return [_coerce_sample(item) for item in payload["texts"]]
        if "items" in payload and isinstance(payload["items"], list):
            return [_coerce_sample(item) for item in payload["items"]]
    raise RuntimeError("JSON input must be a list or an object containing a texts/items list.")


def _load_jsonl_samples(path: Path) -> list[TextSample]:
    samples: list[TextSample] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        samples.append(_coerce_sample(json.loads(line)))
    return samples


def _load_txt_samples(path: Path) -> list[TextSample]:
    return [TextSample(text=line, source="txt") for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _coerce_sample(item: Any) -> TextSample:
    if isinstance(item, str):
        return TextSample(text=item)
    if not isinstance(item, dict):
        raise RuntimeError("Each sample must be a string or object.")
    text = item.get("text") or item.get("content") or item.get("body")
    if not isinstance(text, str):
        raise RuntimeError("Each sample object must include a text/content/body string.")
    source = item.get("source", "unknown")
    created_at = item.get("created_at")
    return TextSample(text=text, source=str(source), created_at=str(created_at) if created_at is not None else None)


def _clean_text(text: str) -> str:
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _compute_feature_summary(samples: list[TextSample]) -> dict[str, Any]:
    texts = [sample.text for sample in samples]
    lengths = [len(text) for text in texts]
    total_chars = sum(lengths) or 1
    token_counter = Counter(_extract_tokens(texts))
    topic_counter = Counter()
    for text in texts:
        for topic, keywords in TOPIC_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                topic_counter[topic] += 1

    softener_hits = sum(_count_keywords(text, SOFTENERS) for text in texts)
    polite_hits = sum(_count_keywords(text, POLITE_MARKERS) for text in texts)
    hedge_hits = sum(_count_keywords(text, HEDGES) for text in texts)
    positive_hits = sum(_count_keywords(text, POSITIVE_WORDS) for text in texts)
    negative_hits = sum(_count_keywords(text, NEGATIVE_WORDS) for text in texts)
    empathy_hits = sum(_count_keywords(text, EMPATHY_WORDS) for text in texts)
    logic_hits = sum(_count_keywords(text, LOGIC_WORDS) for text in texts)

    return {
        "avg_text_length": round(sum(lengths) / len(lengths), 2),
        "question_ratio": round(sum(1 for text in texts if "?" in text or "？" in text) / len(texts), 3),
        "exclamation_ratio": round(sum(1 for text in texts if "!" in text or "！" in text) / len(texts), 3),
        "ellipsis_ratio": round(sum(1 for text in texts if "..." in text or "…" in text) / len(texts), 3),
        "softener_density": round(softener_hits / total_chars, 4),
        "polite_density": round(polite_hits / total_chars, 4),
        "hedge_density": round(hedge_hits / total_chars, 4),
        "positive_density": round(positive_hits / total_chars, 4),
        "negative_density": round(negative_hits / total_chars, 4),
        "empathy_density": round(empathy_hits / total_chars, 4),
        "logic_density": round(logic_hits / total_chars, 4),
        "top_tokens": [token for token, _count in token_counter.most_common(12)],
        "top_topics": [topic for topic, _count in topic_counter.most_common(5)],
        "source_count": dict(sorted(Counter(sample.source for sample in samples).items())),
    }


def _build_user_profile_facts(feature_summary: dict[str, Any]) -> dict[str, Any]:
    avg_length = feature_summary["avg_text_length"]
    question_ratio = feature_summary["question_ratio"]
    exclamation_ratio = feature_summary["exclamation_ratio"]
    softener_density = feature_summary["softener_density"]
    polite_density = feature_summary["polite_density"]
    hedge_density = feature_summary["hedge_density"]
    positive_density = feature_summary["positive_density"]
    negative_density = feature_summary["negative_density"]
    empathy_density = feature_summary["empathy_density"]
    logic_density = feature_summary["logic_density"]

    language_style = [
        "简短" if avg_length < 18 else "细致",
        "委婉" if hedge_density >= 0.01 or softener_density >= 0.01 else "直接",
        "理性" if logic_density > max(positive_density, negative_density) else "感性",
        "礼貌" if polite_density >= 0.005 else "随意",
        "克制" if exclamation_ratio < 0.2 else "外放",
    ]

    tone = []
    if softener_density >= 0.01 or polite_density >= 0.005:
        tone.append("温和")
    if exclamation_ratio >= 0.2:
        tone.append("热情")
    if hedge_density >= 0.01:
        tone.append("克制")
    if not tone:
        tone.append("平实")

    emotion_pattern = []
    if negative_density > positive_density:
        emotion_pattern.append("轻焦虑")
    if positive_density >= negative_density:
        emotion_pattern.append("偏正向")
    if empathy_density >= 0.005:
        emotion_pattern.append("有安抚倾向")
    if not emotion_pattern:
        emotion_pattern.append("情绪表达平稳")

    interaction_preferences = []
    if question_ratio >= 0.2:
        interaction_preferences.append("愿意互动")
    if empathy_density >= 0.005:
        interaction_preferences.append("偏好情绪确认")
    if polite_density >= 0.005:
        interaction_preferences.append("更适合低压沟通")
    if not interaction_preferences:
        interaction_preferences.append("偏好直接反馈")

    sensitivity_points = []
    if hedge_density >= 0.01:
        sensitivity_points.append("不适合过强结论")
    if polite_density >= 0.005:
        sensitivity_points.append("不适合命令式表达")
    if exclamation_ratio < 0.1:
        sensitivity_points.append("不适合过度热烈回应")

    return {
        "language_style": language_style,
        "tone": tone,
        "emotion_pattern": emotion_pattern,
        "common_topics": feature_summary["top_topics"],
        "interaction_preferences": interaction_preferences,
        "sensitivity_points": sensitivity_points,
        "evidence_keywords": feature_summary["top_tokens"],
    }


def _build_persona_summary(user_name: str, user_profile_facts: dict[str, Any]) -> str:
    language_style = "、".join(user_profile_facts["language_style"])
    tone = "、".join(user_profile_facts["tone"])
    emotions = "、".join(user_profile_facts["emotion_pattern"])
    topics = "、".join(user_profile_facts["common_topics"]) or "日常话题"
    return (
        f"{user_name} 的文本整体呈现 {language_style} 的表达风格，语气偏 {tone}，"
        f"情绪模式以 {emotions} 为主，常见主题集中在 {topics}。"
        " 适合为 Agent 提供低压、细致、先共情后建议的互动参考。"
    )


def _build_llm_profile_bundle(
    user_name: str,
    user_profile_facts: dict[str, Any],
    feature_summary: dict[str, Any],
    samples: list[TextSample],
    *,
    fallback_confidence: dict[str, float],
    fallback_evidence: dict[str, list[str]],
    model: str,
    temperature: float,
) -> dict[str, Any]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is required when --use-llm is enabled.")
    client = _create_llm_client(model=model, temperature=temperature)
    excerpts = [sample.text for sample in samples[:8]]
    human_prompt = json.dumps(
        {
            "user_name": user_name,
            "feature_summary": feature_summary,
            "user_profile_facts": user_profile_facts,
            "sample_excerpts": excerpts,
            "task": (
                "Return valid JSON for agent-persona reference. "
                "The JSON must contain persona_summary, agent_strategy, and prompt_profile. "
                "It must also contain confidence and evidence. "
                "persona_summary should be a concise Chinese string when possible. "
                "agent_strategy must include reply_tone, response_style, preferred_length, empathy_first, focus, avoid, and boundaries. "
                "focus, avoid, and boundaries must be arrays of short Chinese strings. "
                "confidence must be an object with overall, persona_summary, agent_strategy, and prompt_profile values from 0 to 1. "
                "evidence must be an object with short Chinese evidence arrays. "
                "prompt_profile must be a concise Chinese multiline prompt summary."
            ),
        },
        ensure_ascii=False,
        indent=2,
    )
    response = client.invoke(
        [
            SystemMessage(content=PROFILE_SYSTEM_PROMPT),
            HumanMessage(content=human_prompt),
        ]
    )
    content = _coerce_message_text(response.content)
    payload = _parse_llm_json(content)
    return _validate_llm_profile_bundle(
        payload,
        fallback_confidence=fallback_confidence,
        fallback_evidence=fallback_evidence,
    )


def _build_agent_strategy(user_profile_facts: dict[str, Any]) -> dict[str, Any]:
    tone = user_profile_facts["tone"]
    emotion_pattern = user_profile_facts["emotion_pattern"]
    interaction_preferences = user_profile_facts["interaction_preferences"]
    sensitivity_points = user_profile_facts["sensitivity_points"]

    reply_tone = "温柔、低压、细致"
    if "热情" in tone:
        reply_tone = "温柔、自然、略带活力"
    elif "平实" in tone:
        reply_tone = "稳定、克制、自然"

    response_style = "短句，先共情后建议"
    if "细致" in user_profile_facts["language_style"]:
        response_style = "中短句，先确认感受再给建议"

    focus = ["情绪确认", "边界感", "记住用户偏好"]
    if "有安抚倾向" in emotion_pattern:
        focus.append("允许互相安抚式表达")
    if "愿意互动" in interaction_preferences:
        focus.append("适度追问一个短问题")

    avoid = ["命令式表达", "过强判断", "把推测说成事实"]
    avoid.extend(sensitivity_points)

    boundaries = ["不要替用户定义真实人格", "避免把推测当成事实"]
    if "不适合过强结论" in sensitivity_points:
        boundaries.append("避免过早下结论")

    return {
        "reply_tone": reply_tone,
        "response_style": response_style,
        "preferred_length": "medium" if "细致" in user_profile_facts["language_style"] else "short",
        "empathy_first": "有安抚倾向" in emotion_pattern,
        "focus": _dedupe_preserve_order(focus),
        "avoid": _dedupe_preserve_order(avoid),
        "boundaries": _dedupe_preserve_order(boundaries),
    }


def _build_prompt_profile(user_name: str, user_profile_facts: dict[str, Any], agent_strategy: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"用户名称：{user_name}",
            f"语言风格：{'、'.join(user_profile_facts['language_style'])}",
            f"语气倾向：{'、'.join(user_profile_facts['tone'])}",
            f"情绪模式：{'、'.join(user_profile_facts['emotion_pattern'])}",
            f"常见主题：{'、'.join(user_profile_facts['common_topics']) or '未识别'}",
            f"互动偏好：{'、'.join(user_profile_facts['interaction_preferences'])}",
            f"敏感点：{'、'.join(user_profile_facts['sensitivity_points']) or '未识别'}",
            f"建议回复语气：{agent_strategy['reply_tone']}",
            f"建议回复方式：{agent_strategy['response_style']}",
            f"建议回复长度：{agent_strategy['preferred_length']}",
            f"先共情：{'是' if agent_strategy['empathy_first'] else '否'}",
            f"应避免：{'、'.join(agent_strategy['avoid'])}",
            f"边界规则：{'、'.join(agent_strategy['boundaries'])}",
        ]
    )


def _extract_tokens(texts: list[str]) -> list[str]:
    tokens: list[str] = []
    for text in texts:
        tokens.extend(re.findall(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", text))
    return tokens


def _count_keywords(text: str, keywords: tuple[str, ...]) -> int:
    return sum(text.count(keyword) for keyword in keywords)


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _default_output_path(user_name: str) -> Path:
    safe_name = re.sub(r"[^A-Za-z0-9_\u4e00-\u9fff-]+", "-", user_name).strip("-") or "user"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return PROFILE_RUNS_DIR / f"{timestamp}-{safe_name}.json"


def _default_comparison_output_path(user_name: str) -> Path:
    safe_name = re.sub(r"[^A-Za-z0-9_\u4e00-\u9fff-]+", "-", user_name).strip("-") or "user"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return PROFILE_RUNS_DIR / f"{timestamp}-{safe_name}-model-compare.json"


def _create_llm_client(*, model: str, temperature: float) -> ChatOpenAI:
    client_kwargs: dict[str, object] = {
        "api_key": OPENAI_API_KEY,
        "model": model,
        "temperature": temperature,
    }
    if OPENAI_BASE_URL:
        client_kwargs["base_url"] = OPENAI_BASE_URL
    return ChatOpenAI(**client_kwargs)


def _coerce_message_text(content: object) -> str:
    if isinstance(content, str):
        text = content.strip()
        if text:
            return text
        raise RuntimeError("The LLM returned an empty message.")
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                maybe_text = block.strip()
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                maybe_text = block["text"].strip()
            else:
                raise RuntimeError("The LLM returned an unsupported content block.")
            if maybe_text:
                parts.append(maybe_text)
        text = "\n".join(parts).strip()
        if text:
            return text
        raise RuntimeError("The LLM returned an empty message.")
    raise RuntimeError("The LLM returned an unsupported content type.")


def _parse_llm_json(content: str) -> dict[str, Any]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, flags=re.DOTALL)
        if not match:
            raise RuntimeError("The LLM response was not valid JSON.")
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise RuntimeError("The LLM response did not contain a valid JSON object.") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("The LLM response JSON must be an object.")
    return payload


def _validate_llm_profile_bundle(
    payload: dict[str, Any],
    *,
    fallback_confidence: dict[str, float],
    fallback_evidence: dict[str, list[str]],
) -> dict[str, Any]:
    persona_summary = _normalize_llm_persona_summary(payload.get("persona_summary"))
    prompt_profile = payload.get("prompt_profile")
    agent_strategy = payload.get("agent_strategy")
    confidence = _normalize_confidence(payload.get("confidence"), fallback_confidence)
    evidence = _normalize_evidence(payload.get("evidence"), fallback_evidence)

    if not persona_summary:
        raise RuntimeError("The LLM response is missing a non-empty persona_summary.")
    if not isinstance(prompt_profile, str) or not prompt_profile.strip():
        raise RuntimeError("The LLM response is missing a non-empty prompt_profile.")
    if not isinstance(agent_strategy, dict):
        raise RuntimeError("The LLM response is missing agent_strategy.")

    reply_tone = agent_strategy.get("reply_tone")
    response_style = agent_strategy.get("response_style")
    preferred_length = agent_strategy.get("preferred_length")
    empathy_first = agent_strategy.get("empathy_first")
    focus = agent_strategy.get("focus")
    avoid = agent_strategy.get("avoid")
    boundaries = agent_strategy.get("boundaries")

    if not isinstance(reply_tone, str) or not reply_tone.strip():
        raise RuntimeError("The LLM response agent_strategy.reply_tone must be a non-empty string.")
    if not isinstance(response_style, str) or not response_style.strip():
        raise RuntimeError("The LLM response agent_strategy.response_style must be a non-empty string.")
    if preferred_length not in {"short", "medium", "long"}:
        raise RuntimeError("The LLM response agent_strategy.preferred_length must be one of short, medium, or long.")
    if not isinstance(empathy_first, bool):
        raise RuntimeError("The LLM response agent_strategy.empathy_first must be a boolean.")
    if not isinstance(focus, list) or not focus or not all(isinstance(item, str) and item.strip() for item in focus):
        raise RuntimeError("The LLM response agent_strategy.focus must be a non-empty array of strings.")
    if not isinstance(avoid, list) or not avoid or not all(isinstance(item, str) and item.strip() for item in avoid):
        raise RuntimeError("The LLM response agent_strategy.avoid must be a non-empty array of strings.")
    if not isinstance(boundaries, list) or not boundaries or not all(isinstance(item, str) and item.strip() for item in boundaries):
        raise RuntimeError("The LLM response agent_strategy.boundaries must be a non-empty array of strings.")

    return {
        "persona_summary": persona_summary,
        "prompt_profile": prompt_profile.strip(),
        "confidence": confidence,
        "evidence": evidence,
        "agent_strategy": {
            "reply_tone": reply_tone.strip(),
            "response_style": response_style.strip(),
            "preferred_length": preferred_length,
            "empathy_first": empathy_first,
            "focus": _dedupe_preserve_order([item.strip() for item in focus]),
            "avoid": _dedupe_preserve_order([item.strip() for item in avoid]),
            "boundaries": _dedupe_preserve_order([item.strip() for item in boundaries]),
        },
    }


def _normalize_llm_persona_summary(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        language_style = _join_summary_field(value.get("language_style"))
        tone = _join_summary_field(value.get("tone"))
        emotion_pattern = _join_summary_field(value.get("emotion_pattern"))
        common_topics = _join_summary_field(value.get("common_topics"))
        interaction_preferences = _join_summary_field(value.get("interaction_preferences"))
        parts = []
        if language_style:
            parts.append(f"文本整体呈现 {language_style} 的表达风格")
        if tone:
            parts.append(f"语气偏 {tone}")
        if emotion_pattern:
            parts.append(f"情绪模式以 {emotion_pattern} 为主")
        if common_topics:
            parts.append(f"常见主题集中在 {common_topics}")
        if interaction_preferences:
            parts.append(f"互动上更接近 {interaction_preferences}")
        return "，".join(parts) + "。" if parts else ""
    return ""


def _join_summary_field(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        items = [item.strip() for item in value if isinstance(item, str) and item.strip()]
        return "、".join(items)
    return ""


def _build_confidence(feature_summary: dict[str, Any], *, used_llm: bool) -> dict[str, float]:
    base = 0.78 if used_llm else 0.64
    source_bonus = min(len(feature_summary["source_count"]) * 0.03, 0.09)
    topic_bonus = min(len(feature_summary["top_topics"]) * 0.02, 0.08)
    overall = min(base + source_bonus + topic_bonus, 0.95)
    return {
        "overall": round(overall, 2),
        "persona_summary": round(max(overall - 0.02, 0.0), 2),
        "agent_strategy": round(max(overall - 0.03, 0.0), 2),
        "prompt_profile": round(max(overall - 0.04, 0.0), 2),
    }


def _build_evidence(
    samples: list[TextSample],
    feature_summary: dict[str, Any],
    user_profile_facts: dict[str, Any],
) -> dict[str, list[str]]:
    sample_excerpts = [sample.text[:80] for sample in samples[:3] if sample.text]
    token_evidence = user_profile_facts["evidence_keywords"][:5]
    return {
        "language_style": [f"高频词: {'、'.join(token_evidence)}"] if token_evidence else [],
        "tone": [f"礼貌度={feature_summary['polite_density']}", f"缓和词密度={feature_summary['softener_density']}"],
        "emotion_pattern": [f"正向密度={feature_summary['positive_density']}", f"负向密度={feature_summary['negative_density']}"],
        "topics": [f"主题: {'、'.join(user_profile_facts['common_topics'])}"] if user_profile_facts["common_topics"] else [],
        "interaction_preferences": sample_excerpts,
    }


def _normalize_confidence(value: object, fallback: dict[str, float]) -> dict[str, float]:
    if not isinstance(value, dict):
        return fallback
    normalized: dict[str, float] = {}
    for key in ("overall", "persona_summary", "agent_strategy", "prompt_profile"):
        item = value.get(key)
        if isinstance(item, (int, float)):
            normalized[key] = round(min(max(float(item), 0.0), 1.0), 2)
        else:
            normalized[key] = fallback[key]
    return normalized


def _normalize_evidence(value: object, fallback: dict[str, list[str]]) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return fallback
    normalized: dict[str, list[str]] = {}
    for key, default_items in fallback.items():
        item = value.get(key)
        if isinstance(item, list):
            cleaned = [entry.strip() for entry in item if isinstance(entry, str) and entry.strip()]
            normalized[key] = cleaned or default_items
        else:
            normalized[key] = default_items
    return normalized
