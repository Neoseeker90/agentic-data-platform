# Agentic Data Platform — Architecture

## 1. High-Level System Overview

```mermaid
graph TB
    subgraph "User Interfaces"
        UI[Chat UI<br/>chat.html]
        API_CLIENT[API Clients<br/>curl / Slack / etc]
    end

    subgraph "Platform API  :8000"
        ROUTER_HTTP[FastAPI<br/>agent / runs / feedback / skills]
        SESSION[Session Store<br/>PostgreSQL conversation_turns]
    end

    subgraph "Routing & Orchestration"
        ROUTER[Intent Router<br/>Claude Haiku · classify_request_v1]
        LIFECYCLE[Run Lifecycle<br/>plan → context → validate → execute → format]
    end

    subgraph "Skills"
        S1[execute_data_question<br/>queries + charts]
        S2[discover_metrics_and_dashboards<br/>find assets]
        S3[explain_metric_definition<br/>what does X mean?]
        S4[answer_business_question<br/>qualitative answers]
    end

    subgraph "Data Sources"
        LIGHTDASH[Lightdash API<br/>dashboards · explores · search]
        DBT[dbt Manifest<br/>metrics · models · semantic layer]
        DOCS[Business Docs<br/>PostgreSQL FTS]
    end

    subgraph "Semantic Layer"
        VECTOR[pgvector<br/>semantic_embeddings<br/>1024-dim HNSW]
        TITAN[Bedrock Titan Embed v2<br/>eu-central-1]
        INDEXER[SemanticIndexer<br/>background task at startup]
    end

    subgraph "Chart Creation"
        YAML_GEN[YAML Generator<br/>chart + dashboard YAML]
        LHCLI[lightdash upload CLI<br/>agent_content/ directory]
    end

    subgraph "Persistence"
        PG[(PostgreSQL 16<br/>runs · plans · feedback<br/>eval_cases · embeddings)]
        REDIS[(Redis)]
        S3[(LocalStack S3)]
    end

    subgraph "LLM Backend"
        BEDROCK[AWS Bedrock eu-central-1<br/>Claude Haiku — routing/planning<br/>Claude Haiku — execution]
    end

    UI --> ROUTER_HTTP
    API_CLIENT --> ROUTER_HTTP
    ROUTER_HTTP --> SESSION
    ROUTER_HTTP --> ROUTER
    ROUTER --> LIFECYCLE
    LIFECYCLE --> S1 & S2 & S3 & S4
    S1 & S2 & S3 & S4 --> LIGHTDASH & DBT & DOCS
    S1 & S2 & S3 & S4 --> VECTOR
    VECTOR --> TITAN
    INDEXER --> TITAN
    INDEXER --> LIGHTDASH & DBT
    INDEXER --> VECTOR
    S1 --> YAML_GEN --> LHCLI --> LIGHTDASH
    LIFECYCLE --> BEDROCK
    LIFECYCLE --> PG
    ROUTER_HTTP --> PG & REDIS
```

---

## 2. Request Lifecycle

Every user message goes through a deterministic pipeline with full audit trail:

```mermaid
sequenceDiagram
    participant U as User (Chat UI)
    participant API as FastAPI
    participant SS as Session Store
    participant R as Intent Router
    participant L as Run Lifecycle
    participant SK as Skill
    participant DB as PostgreSQL
    participant LLM as Claude Haiku (Bedrock)

    U->>API: POST /agent/ask {request_text, session_id}
    API->>SS: get_history(session_id) → last 10 turns
    SS->>API: conversation history
    API->>API: build_contextual_request(text, history)
    API->>DB: RunStore.create() → run_id
    API->>SS: save_turn(user, text)
    API-->>U: 202 Accepted {run_id, session_id}

    Note over API,LLM: Background asyncio.create_task

    API->>R: route(run) → RouterDecision
    R->>LLM: classify_request_v1 prompt
    LLM-->>R: {skill_name, confidence}
    R-->>API: decision

    API->>DB: update_state(ROUTED, selected_skill)
    API->>L: execute_run(run)

    L->>SK: plan(request_text, run)
    SK->>LLM: planning prompt
    LLM-->>SK: structured plan JSON
    L->>DB: record_plan()

    L->>SK: build_context(plan, run)
    SK->>SK: semantic search → vector DB
    SK->>SK: keyword fallback if empty
    L->>DB: record_context_pack()

    L->>SK: validate(plan, context)
    L->>DB: record_validation()

    L->>SK: execute(plan, context)
    SK->>LLM: execution prompt
    LLM-->>SK: answer / rankings JSON
    L->>DB: record_execution_result()

    L->>SK: format_result(result)
    L->>DB: record_final_response(formatted)
    L->>DB: update_state(SUCCEEDED)

    API->>SS: save_turn(assistant, response)

    U->>API: GET /runs/{run_id}
    API-->>U: {state, response, selected_skill}
```

---

## 3. Four Skills — Capabilities & Routing

```mermaid
graph LR
    Q[User Query] --> R{Intent Router<br/>Claude Haiku}

    R -->|"What was net sales last month?"<br/>breakdown · trend · numbers| S1

    R -->|"What dashboards exist?"<br/>discovery · navigation| S2

    R -->|"What does CM3 mean?"<br/>definition · calculation| S3

    R -->|"Why did revenue drop?"<br/>qualitative · conceptual| S4

    subgraph S1[execute_data_question]
        P1[Planner: map question<br/>to Lightdash explore + fields]
        E1[Executor: runQuery API<br/>+ create chart YAML]
        F1[Formatter: text summary<br/>+ dashboard link]
    end

    subgraph S2[discover_metrics_and_dashboards]
        P2[Planner: extract<br/>search terms]
        E2[Executor: LLM ranks<br/>candidates by relevance]
        F2[Formatter: Metrics section<br/>+ Dashboards section]
    end

    subgraph S3[explain_metric_definition]
        P3[Planner: identify<br/>metric name]
        E3[Executor: synthesise<br/>definition from context]
        F3[Formatter: business meaning<br/>+ caveats + SQL]
    end

    subgraph S4[answer_business_question]
        P4[Planner: identify<br/>metrics + dimensions]
        E4[Executor: RAG over<br/>semantic context]
        F4[Formatter: answer + refs<br/>+ suggested dashboards]
    end
```

---

## 4. Context Retrieval — Semantic + Keyword

```mermaid
graph TD
    Q[Query term e.g. 'profit margin'] --> SM{Semantic<br/>Search<br/>available?}

    SM -->|Yes| EMBED[Embed query<br/>Titan v2 1024-dim]
    EMBED --> COSINE[pgvector cosine similarity<br/>HNSW index<br/>min_similarity=0.3]
    COSINE --> RESULTS{Results?}
    RESULTS -->|>0 results| SRCS[ContextSource list]

    RESULTS -->|empty| KW
    SM -->|No / error| KW[Keyword Fallback]
    KW --> LS[Lightdash search API<br/>dashboards · charts · fields]
    KW --> DM[dbt metric search<br/>name + label + description]
    LS & DM --> SRCS

    SRCS --> DEDUP[Deduplicate by object_ref]
    DEDUP --> CAP[Cap at 30 sources]
    CAP --> CONTEXT[ContextPack → LLM]

    subgraph "What's indexed in pgvector"
        I1[5 dbt metrics<br/>net_sales, cm3_eur, cogs...]
        I2[3 Lightdash-exposed models<br/>fct_amazon_kpi_performance etc]
        I3[4 dashboards]
        I4[133 Lightdash fields<br/>dimensions + metrics from explores]
    end
```

---

## 5. Chart & Dashboard Creation

```mermaid
sequenceDiagram
    participant U as User
    participant SK as execute_data_question
    participant LD as Lightdash API
    participant CLI as lightdash upload CLI
    participant FS as dbt project filesystem

    U->>SK: "build me a dashboard with CM3 per month by BU"

    Note over SK: Planner generates query spec
    SK->>LD: runQuery(explore, dimensions, metrics, filters)
    LD-->>SK: rows + field metadata

    Note over SK: Executor — chart answer_type
    SK->>SK: get_or_create_agent_space()
    SK->>FS: write agent_content/charts/{slug}.yml
    SK->>FS: write agent_content/dashboards/{slug}.yml
    SK->>CLI: lightdash upload --project {uuid} --force --include-charts
    CLI->>LD: POST /api/v1/projects/{uuid}/charts/{slug}/code
    CLI->>LD: POST /api/v1/projects/{uuid}/dashboards/{slug}/code
    CLI-->>SK: Total charts created: 1 / dashboards created: 1

    SK->>LD: GET /api/v1/projects/{uuid}/dashboards
    LD-->>SK: dashboard UUID (slug → UUID lookup)

    SK-->>U: Text summary + [View Dashboard →](lightdash_url/dashboards/{uuid}/view)
```

---

## 6. Semantic Indexer (Startup)

```mermaid
graph TD
    START[API startup<br/>AppContainer.create()] --> BG[asyncio.create_task<br/>SemanticIndexer.run_full_index]

    BG --> CHECK{pgvector<br/>available?}
    CHECK -->|No| SKIP[Skip — log warning<br/>keyword search still works]

    CHECK -->|Yes| IDX_M[Index dbt metrics<br/>name + label + description]
    IDX_M --> IDX_MOD[Index Lightdash-exposed<br/>dbt models only<br/>not all 1500+ staging models]
    IDX_MOD --> IDX_LD[Index Lightdash assets<br/>dashboards + explore fields]

    subgraph "Per content type"
        HASH[Compute SHA-256<br/>of content_text]
        COMPARE{hash changed<br/>vs DB?}
        COMPARE -->|Same| SKIP2[Skip re-embedding]
        COMPARE -->|Different| EMBED2[Call Titan Embed v2<br/>batch_size=10 concurrent]
        EMBED2 --> UPSERT[pgvector upsert<br/>ON CONFLICT UPDATE]
        HASH --> COMPARE
    end

    IDX_M & IDX_MOD & IDX_LD --> HASH
    UPSERT --> STALE[delete_stale:<br/>remove refs no longer in source]
    STALE --> DONE[Log: N items indexed]
```

---

## 7. Conversation Memory & Feedback Loop

```mermaid
graph LR
    subgraph "Conversation Memory"
        ASK[POST /agent/ask<br/>session_id optional] --> HISTORY[Load last 10 turns<br/>from conversation_turns]
        HISTORY --> AUGMENT[Prepend history to request<br/>build_contextual_request]
        AUGMENT --> RUN[Execute run]
        RUN --> SAVE_USER[save_turn: user]
        RUN --> SAVE_ASST[save_turn: assistant]
        SAVE_USER & SAVE_ASST --> PG2[(conversation_turns)]
    end

    subgraph "Feedback Loop"
        THUMB[User clicks thumbs down] --> PANEL[In-chat labelling panel]
        PANEL --> LABEL1[error_label:<br/>wrong_skill · wrong_query<br/>incomplete · hallucination]
        PANEL --> LABEL2[expected_skill dropdown<br/>pre-set to observed skill]
        LABEL1 & LABEL2 --> FB[POST /feedback/{run_id}<br/>helpful=false + labels]
        FB --> EVAL[Background task:<br/>_maybe_create_eval_case]
        EVAL --> EC[(evaluation_cases<br/>status=failing<br/>human_label filled<br/>observed_response stored)]
    end

    EC -.->|future: make run-eval| HARNESS[EvalHarness<br/>routes + scores cases]
    HARNESS -.-> REPORT[Pass rate per skill<br/>regression detection]
```

---

## 8. Data Model (PostgreSQL)

```mermaid
erDiagram
    runs {
        uuid run_id PK
        text user_id
        text interface
        text request_text
        text state
        text selected_skill
        text error_message
        timestamptz created_at
    }

    execution_results {
        uuid result_id PK
        uuid run_id FK
        text formatted_response
        jsonb output
        timestamptz executed_at
    }

    feedback {
        uuid feedback_id PK
        uuid run_id FK
        text user_id
        bool helpful
        text failure_reason
        text error_label
        text expected_skill
        timestamptz captured_at
    }

    evaluation_cases {
        uuid case_id PK
        uuid source_run_id FK
        text request_text
        text expected_skill
        text observed_skill
        text observed_response
        text human_label
        text status
        text created_by
        jsonb dataset_tags
    }

    conversation_turns {
        uuid turn_id PK
        uuid session_id
        uuid run_id FK
        text role
        text content
        timestamptz created_at
    }

    semantic_embeddings {
        uuid embedding_id PK
        text content_type
        text object_ref
        text label
        text content_text
        text content_hash
        vector_1024 embedding
        jsonb metadata
        timestamptz indexed_at
    }

    runs ||--o{ execution_results : "produces"
    runs ||--o{ feedback : "receives"
    runs ||--o{ evaluation_cases : "becomes"
    runs ||--o{ conversation_turns : "belongs to"
```

---

## 9. Technology Stack

| Layer | Technology |
|---|---|
| API | FastAPI + uvicorn |
| LLM | AWS Bedrock — Claude Haiku (routing, planning, execution) |
| Embeddings | AWS Bedrock — Titan Embed v2 (1024-dim) |
| Vector DB | pgvector (PostgreSQL extension) with HNSW index |
| Database | PostgreSQL 16 (runs, feedback, embeddings, sessions) |
| Cache | Redis |
| Object Store | LocalStack S3 (dev) |
| Semantic Layer | dbt (Snowflake, browser SSO) + Lightdash |
| Chart creation | Lightdash CLI (`lightdash upload`) + YAML as code |
| Package manager | uv (Python monorepo, 15 workspace packages) |
| Python | 3.12, async throughout (asyncio, SQLAlchemy async, asyncpg, httpx) |
| Infra | Docker Compose (local dev) |
