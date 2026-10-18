const explanations: Record<string, string> = {
  missing_traversal_evidence: 'Full-menu traversal has not been verified',
  missing_source_evidence: 'Source response evidence is missing',
};

function messages(value: unknown): string[] {
  if (!value) return [];
  if (Array.isArray(value)) return value.flatMap(messages);
  if (typeof value === 'object') {
    const item = value as Record<string, unknown>;
    return messages(item.message ?? item.error ?? item.reason ?? item.code);
  }
  if (typeof value !== 'string') return [];
  const text = value.replace(/\u001b\[[0-?]*[ -/]*[@-~]/g, '').trim();
  // Persisted errors may contain a JSON object followed by verification codes.
  // Find its actual boundary; messages themselves can contain semicolons/braces.
  if (text.startsWith('{') || text.startsWith('[')) {
    let depth = 0, quoted = false, escaped = false;
    for (let index = 0; index < text.length; index++) {
      const character = text[index];
      if (quoted) {
        if (escaped) escaped = false;
        else if (character === '\\') escaped = true;
        else if (character === '"') quoted = false;
      } else if (character === '"') quoted = true;
      else if (character === '{' || character === '[') depth++;
      else if (character === '}' || character === ']') {
        depth--;
        if (depth === 0) {
          try { return [...messages(JSON.parse(text.slice(0, index + 1))), ...messages(text.slice(index + 1).replace(/^\s*;\s*/, ''))]; }
          catch { break; }
        }
      }
    }
  }
  return text.split(/;\s*(?=[a-z]+_[a-z_]+(?:;|$))/).filter(Boolean).map(part => explanations[part] ?? (/^[a-z]+(?:_[a-z]+)+$/.test(part) ? part.replaceAll('_', ' ') : part));
}

export function extractionMessage(value: unknown): string {
  return [...new Set(messages(value))].join(' · ');
}
