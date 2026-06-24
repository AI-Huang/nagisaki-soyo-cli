# nagisaki-soyo-cli

LangChain-based command-line chatbot with a gentle Soyo-style persona.

## Requirements

- Python 3.11+
- An OpenAI-compatible API key in `OPENAI_API_KEY`

## Setup

```bash
uv sync
cp .env.example .env
```

## Run

```bash
uv run nagisaki-soyo-cli
uv run nagisaki-soyo-cli --model gpt-4.1-mini
uv run nagisaki-soyo-cli --prompt "Say hello in a calm tone"
uv run nagisaki-soyo-cli profile-analyze --user-name "长崎素世" --input-file ./sample-user-texts.json
uv run nagisaki-soyo-cli profile-analyze-mysql --user-id 678059f0000000000801f777
uv run nagisaki-soyo-cli profile-analyze-mysql --user-id 678059f0000000000801f777 --use-llm --persist-mysql
uv run nagisaki-soyo-cli profile-compare-mysql --user-id 678059f0000000000801f777 --models gpt-4.1-mini,gpt-4.1-mini
uv run nagisaki-soyo-cli llm-health-probe --models gpt-4.1,gpt-5
```

## Chat commands

- `/help` show in-chat commands
- `/reset` clear the current conversation history
- `/save` write the transcript to `data/transcripts/`
- `/exit` or `/quit` leave the session

## Configuration

Set these in `.env` or your shell:

- `OPENAI_API_KEY` required
- `OPENAI_BASE_URL` optional for OpenAI-compatible providers
- `SOYO_MODEL` optional default model override
- `SOYO_TEMPERATURE` optional default temperature override

The chat model is wired through `langchain-openai` and accepts the same OpenAI-compatible API settings.

## Agent profile scaffold

The repository includes a minimal scaffold for:

1. loading user texts from `.json`, `.jsonl`, or `.txt`
2. computing lightweight language-style features
3. generating a persona summary
4. producing `agent_strategy`, `prompt_profile`, `confidence`, and `evidence`
5. saving the result to `data/profile_runs/`

Run it with:

```bash
uv run nagisaki-soyo-cli profile-analyze \
  --user-name "长崎素世" \
  --input-file ./sample-user-texts.json
```

Use `--use-llm` to generate `persona_summary`, `agent_strategy`, `prompt_profile`, `confidence`, and `evidence` through the configured OpenAI-compatible API. The LLM path expects valid JSON output and raises an explicit error if the response shape is invalid.

To analyze a user directly from the local `xhs_crawler` MySQL database, set these environment variables in `.env`:

- `MYSQL_HOST`
- `MYSQL_PORT`
- `MYSQL_USER`
- `MYSQL_PASSWORD`
- `MYSQL_DATABASE`

Then run:

```bash
uv run nagisaki-soyo-cli profile-analyze-mysql \
  --user-id 678059f0000000000801f777
```

The MySQL-backed scaffold loads `users.bio`, `notes.title`, `notes.desc`, matching `tags.tag`, and any matching `comments.content`, then writes the profile result to `data/profile_runs/`.

Optional persistence target variables:

- `PROFILE_MYSQL_DATABASE`
- `PROFILE_MYSQL_USER_TABLE`
- `PROFILE_MYSQL_PERSONA_TABLE`

To persist the generated profile bundle into the split portrait tables:

```bash
uv run nagisaki-soyo-cli profile-analyze-mysql \
  --user-id 678059f0000000000801f777 \
  --use-llm \
  --persist-mysql
```

To compare one or more models against the same MySQL user input:

```bash
uv run nagisaki-soyo-cli profile-compare-mysql \
  --user-id 678059f0000000000801f777 \
  --models gpt-4.1-mini,gpt-4.1-mini
```

Supported JSON input formats:

```json
[
  {"text": "最近有点累，但还是想把事情做好。", "source": "note"},
  {"text": "谢谢你愿意听我说这些。", "source": "comment"}
]
```

or:

```json
{
  "texts": [
    {"text": "今天心情有点复杂。", "source": "bio"}
  ]
}
```

## MySQL corpus schema

The repository includes a MySQL schema script for the raw dialogue corpus:

```bash
mysql -u <user> -p < sql/mysql_raw_corpus.sql
```

The script creates the database named `nagisaki_soyo_digital_waifu` and the `raw_corpus_entries` table for storing original corpus records.

To inspect a source MySQL database such as `xhs_crawler` and import corpus rows for a user like `长崎素世`, run:

```bash
mysql -u <user> -p < sql/mysql_xhs_crawler_import.sql
```

The import script first queries `information_schema`, then dynamically imports supported `users` and `notes` records into `raw_corpus_entries`.

For Xiaohongshu user characterization, the repository also includes a dedicated profile table schema:

```bash
mysql -u <user> -p < sql/mysql_user_profiles.sql
```

The profile schema now uses two tables:

1. `user_profiles` stores platform user metadata synchronized from `xhs_crawler`
2. `persona_summaries` stores the generated `persona_summary`, `agent_strategy`, `prompt_profile`, confidence, evidence, and other analysis artifacts

To store LLM availability and probe results, apply:

```bash
mysql -u <user> -p < sql/mysql_llm_health.sql
```

The `llm_health` table is intended for recording model call health such as GPT-4 and GPT-5 availability, response previews, and gateway error details.

To batch probe GPT-4/GPT-5 models and automatically persist the result into `llm_health`:

```bash
uv run nagisaki-soyo-cli llm-health-probe
```

To probe a smaller custom set:

```bash
uv run nagisaki-soyo-cli llm-health-probe --models gpt-4.1,gpt-5
```

## Data layout

This project follows the Code-Data Separation Principle.

- Runtime data lives under `$HOME/Data/nagisaki-soyo-cli`
- The repository-local `data/` path is a symlink to that runtime directory
- Saved transcripts are written to `data/transcripts/`