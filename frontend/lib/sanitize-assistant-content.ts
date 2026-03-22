/**
 * Убирает из текста ответа типичные «утечки» аргументов инструментов (JSON, search_query и т.п.).
 */
export function sanitizeAssistantContent(content: string): string {
  if (!content) return content;
  let s = content;
  s = s.replace(
    /\{[\s\S]*?"(?:search_query|tool_calls|function_call|arguments|parameters)"[\s\S]*?\}/g,
    "",
  );
  s = s.replace(
    /```(?:json)?\s*\{[\s\S]*?"search_query"[\s\S]*?\}\s*```/gi,
    "",
  );
  s = s.replace(/\n{3,}/g, "\n\n").trim();
  return s;
}
