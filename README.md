# contentforge

Evidence-grounded pipeline for faceless video content: niche research → sourced script → voice → render → multi-platform publish.

Status: **design phase**. See `docs/superpowers/specs/` for the current design.

## Principles

1. **Provenance or nothing.** Every factual claim resolves to a source with a URL and retrieval timestamp. Stages that lose their inputs fail loudly and write nothing — there are no synthesised fallbacks anywhere in this codebase.
2. **Transform, never relay.** Scripts must not reproduce source material verbatim. Enforced in code, not by convention.
3. **Structure varies per video.** No fixed script template.
4. **Scraping and publishing never share credentials.**

## Layout

    providers/   API clients (YouTube, Instagram, Threads, LLM)
    research/    niche discovery and scoring
    sourcing/    primary source gathering
    script/      generation + the provenance validator
    voice/       TTS
    visuals/     asset acquisition
    render/      ffmpeg composition
    publish/     platform upload
    review/      approve/reject gate

## License

Private. All rights reserved.
