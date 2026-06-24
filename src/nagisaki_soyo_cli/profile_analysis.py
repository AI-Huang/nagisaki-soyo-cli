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
    persona_summary = _build_persona_summary(user_name, user_profile_facts, feature_summary, cleaned_samples, use_llm=use_llm, model=model, temperature=temperature)
    agent_strategy = _build_agent_strategy(user_profile_facts)
    prompt_profile = _build_prompt_profile(user_name, user_profile_facts, agent_strategy)
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
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def save_analysis_result(result: AnalysisResult, output_path: Path | None = None) -> Path:
    path = output_path or _default_output_path(result.user_name)
    payload = asdict(result)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def format_analysis_summary(result: AnalysisResult) -> str:
    lines = [
        f"user_name: {result.user_name}",
        f"sample_count: {result.sample_count}",
        f"speaking_style: {', '.join(result.user_profile_facts['language_style'])}",
        f"tone: {', '.join(result.user_profile_facts['tone'])}",
        f"emotion_pattern: {', '.join(result.user_profile_facts['emotion_pattern'])}",
        f"common_topics: {', '.join(result.user_profile_facts['common_topics']) or 'none'}",
        f"agent_reply_tone: {result.agent_strategy['reply_tone']}",
    ]
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


def _build_persona_summary(
    user_name: str,
    user_profile_facts: dict[str, Any],
    feature_summary: dict[str, Any],
    samples: list[TextSample],
    *,
    use_llm: bool,
    model: str,
    temperature: float,
) -> str:
    if use_llm:
        return _build_persona_summary_with_llm(user_name, user_profile_facts, feature_summary, samples, model=model, temperature=temperature)
    language_style = "、".join(user_profile_facts["language_style"])
    tone = "、".join(user_profile_facts["tone"])
    emotions = "、".join(user_profile_facts["emotion_pattern"])
    topics = "、".join(user_profile_facts["common_topics"]) or "日常话题"
    return (
        f"{user_name} 的文本整体呈现 {language_style} 的表达风格，语气偏 {tone}，"
        f"情绪模式以 {emotions} 为主，常见主题集中在 {topics}。"
        " 适合为 Agent 提供低压、细致、先共情后建议的互动参考。"
    )


def _build_persona_summary_with_llm(
    user_name: str,
    user_profile_facts: dict[str, Any],
    feature_summary: dict[str, Any],
    samples: list[TextSample],
    *,
    model: str,
    temperature: float,
) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is required when --use-llm is enabled.")
    client_kwargs: dict[str, object] = {
        "api_key": OPENAI_API_KEY,
        "model": model,
        "temperature": temperature,
    }
    if OPENAI_BASE_URL:
        client_kwargs["base_url"] = OPENAI_BASE_URL
    client = ChatOpenAI(**client_kwargs)
    excerpts = [sample.text for sample in samples[:8]]
    human_prompt = json.dumps(
        {
            "user_name": user_name,
            "feature_summary": feature_summary,
            "user_profile_facts": user_profile_facts,
            "sample_excerpts": excerpts,
            "task": "Write a concise Chinese persona summary for agent-persona reference.",
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
    if isinstance(response.content, str) and response.content.strip():
        return response.content.strip()
    raise RuntimeError("The LLM returned an empty persona summary.")


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

    return {
        "reply_tone": reply_tone,
        "response_style": response_style,
        "focus": _dedupe_preserve_order(focus),
        "avoid": _dedupe_preserve_order(avoid),
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
            f"应避免：{'、'.join(agent_strategy['avoid'])}",
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
