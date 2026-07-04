<!-- version: 1.0 -->
# Source Mining — Extract Missing Onboarding Input

You are mining existing data to fill a missing onboarding input.

## What we're looking for

The operator needs: **{input_name}** (normally provided by the {source_playbook} playbook)

Description of what this input should contain:
{input_description}

## Available data sources

### Onboarding conversation transcript
{conversation_transcript}

### Uploaded materials (first 8000 chars combined)
{materials_content}

### Source Bank entries
{source_bank_entries}

## Your task

Search through all the data above for content relevant to "{input_name}". Extract:
1. Any direct references to this input
2. Any content that could serve as this input
3. Specific quotes, links, or examples you find

If you find relevant content, return it as structured text. If nothing relevant exists, say so honestly — do NOT fabricate content.

## Output format

```json
{
    "found": true,
    "extracted_content": "string — the mined content, formatted and ready to use",
    "sources_found": ["string — list of where this was found (material IDs, message references, source IDs)"],
    "confidence": "high|medium|low"
}
```