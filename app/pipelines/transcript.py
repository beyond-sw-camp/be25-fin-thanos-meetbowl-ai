def normalize_raw_transcript(raw_transcript: str) -> str:
    """Keep the generation pipeline independent from the upstream transcript shape.

    If the upstream contract later becomes a list of utterances, an adapter should
    sort and join that list before calling this normalization boundary.
    """
    normalized_lines = [" ".join(line.split()) for line in raw_transcript.splitlines()]
    return "\n".join(line for line in normalized_lines if line)
