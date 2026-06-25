from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .chatbot import ChatSession, OPENAI_ERRORS
from .config import DEFAULT_MODEL, DEFAULT_TEMPERATURE
from .demo_persona_chat import build_demo_system_prompt, format_demo_chat_banner
from .llm_health import (
    DEFAULT_LLM_HEALTH_MODELS,
    format_llm_health_summary,
    list_available_chat_models,
    persist_llm_health_records,
    run_llm_health_probe,
)
from .mysql_persona_source import load_persona_mirror_source
from .mysql_profile_source import load_mysql_profile_source
from .mysql_profile_store import persist_analysis_result_to_mysql
from .profile_analysis import (
    analyze_user_language,
    compare_user_language_models,
    format_analysis_summary,
    format_model_comparison_summary,
    load_text_samples,
    save_analysis_result,
    save_model_comparison,
)
from .prompts import DEFAULT_SYSTEM_PROMPT


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nagisaki-soyo-cli",
        description="LangChain-based command-line chatbot with a gentle Soyo persona.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Model name for the OpenAI-compatible API.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=DEFAULT_TEMPERATURE,
        help="Sampling temperature for responses.",
    )
    parser.add_argument(
        "--system-prompt-file",
        type=Path,
        help="Optional file that replaces the built-in system prompt.",
    )
    parser.add_argument(
        "--prompt",
        help="Send one message and print one reply without entering the REPL.",
    )
    parser.add_argument(
        "--save-on-exit",
        action="store_true",
        help="Save the conversation transcript when leaving the chat.",
    )
    parser.add_argument(
        "--no-banner", action="store_true", help="Do not print the startup banner."
    )
    return parser


def build_profile_analyze_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nagisaki-soyo-cli profile-analyze",
        description="Analyze user texts and build an agent-persona reference scaffold.",
    )
    parser.add_argument(
        "--user-name", required=True, help="Display name for the analyzed user."
    )
    parser.add_argument(
        "--input-file",
        type=Path,
        required=True,
        help="Input .json, .jsonl, or .txt file containing the user's texts.",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        help="Optional output JSON path. Defaults to data/profile_runs/<timestamp>-<user>.json.",
    )
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Use the configured OpenAI-compatible LLM to generate the persona summary.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Model name for optional LLM summarization.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=DEFAULT_TEMPERATURE,
        help="Sampling temperature for optional LLM summarization.",
    )
    return parser


def build_profile_analyze_mysql_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nagisaki-soyo-cli profile-analyze-mysql",
        description="Analyze a user's texts directly from the local xhs_crawler MySQL database.",
    )
    parser.add_argument(
        "--user-name",
        help="Display name to match against users.nickname or authors.author_name.",
    )
    parser.add_argument(
        "--user-id", help="Exact user identifier from xhs_crawler.users."
    )
    parser.add_argument(
        "--max-notes",
        type=int,
        default=50,
        help="Maximum number of notes to load from MySQL.",
    )
    parser.add_argument(
        "--max-comments",
        type=int,
        default=50,
        help="Maximum number of comments to load from MySQL.",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        help="Optional output JSON path. Defaults to data/profile_runs/<timestamp>-<user>.json.",
    )
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Use the configured OpenAI-compatible LLM to generate the full profile bundle.",
    )
    parser.add_argument(
        "--persist-mysql",
        action="store_true",
        help="Persist the generated profile bundle into the target MySQL user_profiles and persona_summaries tables.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Model name for optional LLM summarization.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=DEFAULT_TEMPERATURE,
        help="Sampling temperature for optional LLM summarization.",
    )
    return parser


def build_profile_compare_mysql_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nagisaki-soyo-cli profile-compare-mysql",
        description="Compare one or more LLM models against the same xhs_crawler user profile input.",
    )
    parser.add_argument(
        "--user-name",
        help="Display name to match against users.nickname or authors.author_name.",
    )
    parser.add_argument(
        "--user-id", help="Exact user identifier from xhs_crawler.users."
    )
    parser.add_argument(
        "--models",
        required=True,
        help="Comma-separated list of one or more model names to compare.",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        help="Optional output JSON path for comparison results.",
    )
    parser.add_argument(
        "--max-notes",
        type=int,
        default=50,
        help="Maximum number of notes to load from MySQL.",
    )
    parser.add_argument(
        "--max-comments",
        type=int,
        default=50,
        help="Maximum number of comments to load from MySQL.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=DEFAULT_TEMPERATURE,
        help="Sampling temperature for model comparison.",
    )
    return parser


def build_llm_health_probe_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nagisaki-soyo-cli llm-health-probe",
        description="Probe GPT-4/GPT-5 model availability and persist the results into MySQL.",
    )
    parser.add_argument(
        "--models",
        default=",".join(DEFAULT_LLM_HEALTH_MODELS),
        help="Comma-separated model list to probe.",
    )
    parser.add_argument(
        "--request-text",
        default="Reply with ok",
        help="Minimal user prompt sent to each model.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0,
        help="Sampling temperature used for health probes.",
    )
    parser.add_argument(
        "--skip-visible-models",
        action="store_true",
        help="Skip listing visible GPT-4/GPT-5 models before probing.",
    )
    parser.add_argument(
        "--skip-persist",
        action="store_true",
        help="Do not write probe results into the llm_health MySQL table.",
    )
    return parser


def build_demo_chat_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nagisaki-soyo-cli demo-chat",
        description="Chat with a demo bot driven by the latest persisted persona summary.",
    )
    parser.add_argument(
        "--user-name", help="Display name to match against user_profiles.nickname."
    )
    parser.add_argument(
        "--user-id", help="Exact user identifier from user_profiles.source_user_id."
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Model name for the OpenAI-compatible API.",
    )
    parser.add_argument(
        "--no-select-model",
        action="store_true",
        help="Skip the interactive model picker shown before the chat starts.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=DEFAULT_TEMPERATURE,
        help="Sampling temperature for responses.",
    )
    parser.add_argument(
        "--prompt",
        help="Send one message and print one reply without entering the REPL.",
    )
    parser.add_argument(
        "--save-on-exit",
        action="store_true",
        help="Save the conversation transcript when leaving the chat.",
    )
    parser.add_argument(
        "--no-banner", action="store_true", help="Do not print the startup banner."
    )
    return parser


def load_system_prompt(path: Path | None) -> str:
    if path is None:
        return DEFAULT_SYSTEM_PROMPT
    return path.read_text(encoding="utf-8").strip()


def print_banner() -> None:
    print("Soyo is ready. Type /help for commands.")


def print_help() -> None:
    print("/help  show commands")
    print("/model switch the active model")
    print("/reset clear conversation history")
    print("/save  save transcript to data/transcripts/")
    print("/exit  leave the chat")


def select_model(current_model: str) -> str:
    """Prompt the user to pick a model by number, defaulting to current_model.

    Returns the selected model name. Falls back to current_model when input is
    unavailable (non-interactive stdin) or left blank.
    """
    models = list_available_chat_models()
    if current_model not in models:
        models = [current_model, *models]
    print("Available models:")
    for index, name in enumerate(models, start=1):
        marker = " (current)" if name == current_model else ""
        print(f"  {index}. {name}{marker}")
    try:
        choice = input(
            f"Select model [1-{len(models)}, enter to keep {current_model}]: "
        ).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return current_model
    if not choice:
        return current_model
    if choice.isdigit():
        position = int(choice)
        if 1 <= position <= len(models):
            return models[position - 1]
        print(f"Out of range; keeping {current_model}.")
        return current_model
    return choice


def run_repl(session: ChatSession, save_on_exit: bool) -> None:
    while True:
        try:
            user_text = input("you> ").strip()
        except KeyboardInterrupt:
            print("\nInterrupted.")
            break
        except EOFError:
            print()
            break

        if not user_text:
            continue
        if user_text in {"/exit", "/quit"}:
            break
        if user_text == "/help":
            print_help()
            continue
        if user_text == "/model":
            selected = select_model(session.model)
            if selected == session.model:
                print(f"Model unchanged: {session.model}.")
            else:
                session.set_model(selected)
                print(f"Model switched to {session.model}.")
            continue
        if user_text == "/reset":
            session.reset()
            print("Conversation cleared.")
            continue
        if user_text == "/save":
            path = session.save_transcript()
            print(f"Saved transcript to {path}.")
            continue

        try:
            reply = session.reply(user_text)
        except OPENAI_ERRORS as exc:
            print(f"Model request failed: {exc}")
            continue
        print(f"soyo> {reply}")

    if save_on_exit and session.messages:
        path = session.save_transcript()
        print(f"Saved transcript to {path}.")


def main() -> None:
    argv = sys.argv[1:]
    if argv and argv[0] == "profile-analyze":
        parser = build_profile_analyze_parser()
        args = parser.parse_args(argv[1:])
        samples = load_text_samples(args.input_file)
        result = analyze_user_language(
            user_name=args.user_name,
            samples=samples,
            use_llm=args.use_llm,
            model=args.model,
            temperature=args.temperature,
        )
        path = save_analysis_result(result, args.output_file)
        print(format_analysis_summary(result))
        print(f"saved_profile: {path}")
        return
    if argv and argv[0] == "profile-analyze-mysql":
        parser = build_profile_analyze_mysql_parser()
        args = parser.parse_args(argv[1:])
        if not args.user_name and not args.user_id:
            raise SystemExit("profile-analyze-mysql requires --user-name or --user-id.")
        source = load_mysql_profile_source(
            user_name=args.user_name,
            user_id=args.user_id,
            max_notes=args.max_notes,
            max_comments=args.max_comments,
        )
        result = analyze_user_language(
            user_name=source.user_name,
            samples=source.samples,
            use_llm=args.use_llm,
            model=args.model,
            temperature=args.temperature,
        )
        path = save_analysis_result(result, args.output_file)
        if args.persist_mysql:
            persist_analysis_result_to_mysql(source, result)
        print(format_analysis_summary(result))
        print(f"mysql_user_id: {source.user_id}")
        if args.persist_mysql:
            print("persisted_mysql: yes")
        print(f"saved_profile: {path}")
        return
    if argv and argv[0] == "profile-compare-mysql":
        parser = build_profile_compare_mysql_parser()
        args = parser.parse_args(argv[1:])
        if not args.user_name and not args.user_id:
            raise SystemExit("profile-compare-mysql requires --user-name or --user-id.")
        models = [item.strip() for item in args.models.split(",") if item.strip()]
        if not models:
            raise SystemExit("profile-compare-mysql requires at least one model name.")
        source = load_mysql_profile_source(
            user_name=args.user_name,
            user_id=args.user_id,
            max_notes=args.max_notes,
            max_comments=args.max_comments,
        )
        comparison = compare_user_language_models(
            user_name=source.user_name,
            samples=source.samples,
            models=models,
            temperature=args.temperature,
        )
        path = save_model_comparison(comparison, args.output_file)
        print(format_model_comparison_summary(comparison))
        print(f"mysql_user_id: {source.user_id}")
        print(f"saved_comparison: {path}")
        return
    if argv and argv[0] == "llm-health-probe":
        parser = build_llm_health_probe_parser()
        args = parser.parse_args(argv[1:])
        models = [item.strip() for item in args.models.split(",") if item.strip()]
        if not models:
            raise SystemExit("llm-health-probe requires at least one model.")
        result = run_llm_health_probe(
            models=models,
            request_text=args.request_text,
            temperature=args.temperature,
            fetch_visible_models=not args.skip_visible_models,
        )
        if not args.skip_persist:
            persist_llm_health_records(result)
        print(format_llm_health_summary(result))
        if not args.skip_persist:
            print("persisted_mysql: yes")
        return
    if argv and argv[0] == "demo-chat":
        parser = build_demo_chat_parser()
        args = parser.parse_args(argv[1:])
        if not args.user_name and not args.user_id:
            raise SystemExit("demo-chat requires --user-name or --user-id.")
        persona_source = load_persona_mirror_source(
            user_name=args.user_name,
            user_id=args.user_id,
        )
        selected_model = args.model
        if not args.prompt and not args.no_select_model and sys.stdin.isatty():
            selected_model = select_model(args.model)
        session = ChatSession(
            model=selected_model,
            temperature=args.temperature,
            system_prompt=build_demo_system_prompt(persona_source),
        )
        if not args.no_banner:
            print(format_demo_chat_banner(persona_source))
        if args.prompt:
            try:
                reply = session.reply(args.prompt)
            except OPENAI_ERRORS as exc:
                raise SystemExit(f"Model request failed: {exc}") from exc
            print(reply)
            if args.save_on_exit:
                path = session.save_transcript()
                print(f"Saved transcript to {path}.")
            return
        run_repl(session, save_on_exit=args.save_on_exit)
        return

    parser = build_parser()
    args = parser.parse_args(argv)
    system_prompt = load_system_prompt(args.system_prompt_file)
    session = ChatSession(
        model=args.model,
        temperature=args.temperature,
        system_prompt=system_prompt,
    )

    if args.prompt:
        try:
            reply = session.reply(args.prompt)
        except OPENAI_ERRORS as exc:
            raise SystemExit(f"Model request failed: {exc}") from exc
        print(reply)
        if args.save_on_exit:
            path = session.save_transcript()
            print(f"Saved transcript to {path}.")
        return

    if not args.no_banner:
        print_banner()
    run_repl(session, save_on_exit=args.save_on_exit)
