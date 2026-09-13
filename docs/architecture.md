# Architecture

Diagrams reflect the current, fully-built state of the app (see
`docs/CLAUDE.md` "Current state" / `docs/PROGRESS.md` for the build log).
Regenerate this file if the module layout, pipeline, or schema changes
materially — read the actual code, don't hand-wave.

## 1. System / deployment architecture

One `docker compose` stack on `localhost` — no TLS, no reverse proxy, no
remote deploy (by design; this is a single-professor prototype). The
professor's browser is the only software client; the printer, the printed
sheet, and the student's pen are physical-world actors outside the app.

```mermaid
graph TD
    Prof(["Professor's browser"])
    Printer[/"Printer"/]
    Student[/"Student with pen and paper"/]
    Phone[/"Phone camera or scanner"/]

    subgraph compose["docker compose - localhost only"]
        App["app<br/>Django + gunicorn + WhiteNoise"]
        Worker[["worker<br/>Django-Q2 cluster"]]
        DB[("Postgres")]
        Blob[("Blob volume<br/>PDFs + scanned photos")]
    end

    Prof -->|"HTTP :8010"| App
    App --> DB
    App --> Blob
    App -->|"enqueue batch scan jobs"| Worker
    Worker --> DB
    Worker --> Blob

    App -->|"question paper and answer sheet PDF"| Printer
    Printer -->|"printed sheet"| Student
    Student -->|"fills bubbles"| Phone
    Phone -->|"photo or scanned batch PDF"| Prof
```

## 2. Module architecture

The Django web layer is a thin shell around two **pure, framework-free**
engines — `app/grading` and `app/omr` must stay importable with zero
web-framework imports (`docs/CLAUDE.md` rule 7), so they're testable in
isolation and the scoring/alignment math can never accidentally depend on a
request context. `app/pdf` and the OMR pipeline share one geometry source of
truth: `config/sheet_template.json`.

```mermaid
graph TD
    subgraph web["app/web (views, forms, urls)"]
        quiz_views
        review_views
        scan_views
        forms
    end

    subgraph core["app/core (services, orchestration, persistence)"]
        models["models.py"]
        services["services.py<br/>xlsx_ingest.py, ingest.py"]
        versioning_service
        scan_pipeline
        review_service
        blob_storage
    end

    subgraph grading["app/grading (pure, no web imports)"]
        scoring["scoring.py<br/>score_question - R7"]
        versioning["versioning.py<br/>generate_versions"]
        regrade
    end

    subgraph omr["app/omr (pure, no web imports)"]
        detect["detect.py<br/>fiducials and QR"]
        alignment["alignment.py, geometry.py<br/>homography"]
        crop
        classify["classify.py<br/>bubble fill and confidence gate"]
    end

    subgraph pdf["app/pdf"]
        answer_sheet
        question_paper
        artifacts
    end

    cfg["config/sheet_template.json"]
    DB2[("Postgres")]
    Blob2[("Blob volume")]

    web --> core
    core --> grading
    core --> pdf
    scan_pipeline --> omr
    scan_pipeline --> grading
    pdf --> cfg
    omr --> cfg
    core --> blob_storage
    blob_storage --> Blob2
    core --> DB2
```

## 3. End-to-end pipeline

One quiz's full life, from question upload to a reviewed result. Every
`FAILED` / `NEEDS_REVIEW` exit is a deliberate clean-failure — a bad scan
never gets silently graded against the wrong key.

```mermaid
flowchart TD
    A(["Professor creates quiz"]) --> B["Upload .xlsx questions"]
    B --> C{"All-or-nothing validation"}
    C -->|"invalid"| B
    C -->|"valid"| D["Questions ingested"]
    D --> E["Generate M versions<br/>shuffle + anti-cluster, R2.5"]
    E --> F["Render and cache PDFs<br/>question paper, answer sheet"]
    F --> G[/"Print and distribute"/]
    G --> H[/"Student fills bubbles"/]
    H --> I["Scan: single photo or batch PDF"]
    I --> J{"Align: QR + fiducials,<br/>then timing-mark homography"}
    J -->|"fails"| K["Submission: FAILED<br/>qr_unreadable or alignment_failed"]
    J -->|"ok"| L["Classify bubbles and<br/>un-shuffle to canonical answers"]
    L --> M["Score - shared score_question, R7"]
    M --> N{"Any answer flagged?<br/>low confidence or ambiguous"}
    N -->|"yes"| O["Submission: NEEDS_REVIEW"]
    N -->|"no"| P["Submission: FINALIZED"]
    O --> Q["Professor reviews and overrides<br/>re-scores, audit-logged"]
    Q --> P
    K --> R["Results dashboard and CSV export"]
    P --> R
```

## 4. Database schema (ER diagram)

Eight domain tables. `Version.question_order` / `option_order` / `qr_id` are
immutable after creation (R2.7, enforced in `save()` **and** a DB trigger);
`AuditEvent` rows are append-only (R6.5, DB trigger blocks `UPDATE`).
`Answer.question_no` is a **denormalized canonical index** correlated to
`Question.order_index` within the same quiz — it is not a foreign key (every
printed version shuffles question order and bubble position, so the FK would
have to point at a different `Question` per version anyway).

```mermaid
erDiagram
    PROFESSOR ||--o{ QUIZ : owns
    QUIZ ||--|{ QUESTION : contains
    QUIZ ||--o{ VERSION : generates
    QUIZ ||--o{ ROSTER_ENTRY : has
    QUIZ ||--o{ AUDIT_EVENT : logs
    VERSION ||--o{ SUBMISSION : "scanned as"
    ROSTER_ENTRY |o--o{ SUBMISSION : "assigned to"
    SUBMISSION ||--|{ ANSWER : has
    SUBMISSION |o--o{ SUBMISSION : duplicate_of
    SUBMISSION ||--o{ AUDIT_EVENT : records
    PROFESSOR |o--o{ AUDIT_EVENT : "actor, null means system"

    PROFESSOR {
        int id PK
        string email UK
        bool is_active
    }
    QUIZ {
        int id PK
        int professor_id FK
        string title
        int options_per_question
        string marking_mode
        bool negative_marking
        float default_points
        string status "draft, versioned, or printed"
    }
    QUESTION {
        int id PK
        int quiz_id FK
        int order_index "canonical position"
        text text
        json options
        json correct_options
        float points "nullable, falls back to quiz.default_points"
    }
    VERSION {
        int id PK
        int quiz_id FK
        int version_number
        uuid qr_id UK "immutable"
        json question_order "immutable"
        json option_order "immutable"
        int template_version
        datetime printed_at
        bool anticluster_fallback
    }
    ROSTER_ENTRY {
        int id PK
        int quiz_id FK
        string label
        string external_id
    }
    SUBMISSION {
        int id PK
        int version_id FK
        int roster_entry_id FK "nullable"
        int duplicate_of_id FK "nullable, self reference"
        string status "pending, needs_review, finalized, or failed"
        string failure_reason
        float total_score "null until finalized"
        string source "photo or batch_pdf"
        string raw_image_path
    }
    ANSWER {
        int id PK
        int submission_id FK
        int question_no "denormalized, not a FK"
        json detected_options
        float confidence
        bool flagged
        bool correct
        float score
        bool manually_edited
    }
    AUDIT_EVENT {
        int id PK
        int quiz_id FK
        int submission_id FK "nullable"
        int actor_professor_id FK "nullable means system"
        string action
        json detail
        datetime created_at "append-only"
    }
```
