import re

def clean_travel_response(text: str) -> str:
    """
    Sanitizes LLM outputs for travel assistant responses:
    - Strips <think>...</think> reasoning blocks (and unclosed <think> blocks).
    - Strips markdown code blocks/fences (```markdown ... ```, ```json ... ```, ``` ... ```).
    - Converts HTML elements like <br>, <ul>, <li> to clean markdown.
    - Transforms markdown tables (| Item | Details |) into clear readable bullet points.
    - Strips stray brackets or code artifacts.
    """
    if not text:
        return ""
        
    s = str(text).strip()
    
    # 1. Remove reasoning / think blocks
    if "<think>" in s:
        if "</think>" in s:
            s = re.sub(r"<think>.*?</think>", "", s, flags=re.DOTALL).strip()
        else:
            # Unclosed think tag: strip everything from <think> onwards or take after if thought is at start
            parts = s.split("<think>")
            s = parts[0].strip() if parts[0].strip() else ""
            
    if "<reasoning>" in s and "</reasoning>" in s:
        s = re.sub(r"<reasoning>.*?</reasoning>", "", s, flags=re.DOTALL).strip()
        
    # 2. Strip code block fences completely
    s = re.sub(r"^```[a-zA-Z0-9_-]*\s*\n?", "", s, flags=re.MULTILINE)
    s = re.sub(r"\n?```\s*$", "", s, flags=re.MULTILINE)
    s = re.sub(r"```+", "", s)
    
    # 3. Clean HTML tags
    # Convert <br>, <br/>, <br /> to newlines
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.IGNORECASE)
    # Convert <li> to bullet
    s = re.sub(r"<li>\s*", "- ", s, flags=re.IGNORECASE)
    s = re.sub(r"</li>", "\n", s, flags=re.IGNORECASE)
    # Strip other HTML tags like <ul>, </ul>, <ol>, </ol>, <div>, </div>, <p>, </p>, <b>, </b>, <span>, </span>
    s = re.sub(r"</?[a-zA-Z][^>]*>", "", s)
    
    # 4. Convert Markdown tables to clean bullet lists
    # Detect markdown table lines e.g. | Key | Value |
    lines = s.split("\n")
    cleaned_lines = []
    
    for line in lines:
        trimmed = line.strip()
        # Table separator line e.g. |---|---|
        if re.match(r"^\|?\s*[-:]+\s*\|\s*[-:]+\s*\|?$", trimmed):
            continue
            
        # Table data row e.g. | **Item** | Details |
        table_row_match = re.match(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|?$", trimmed)
        if table_row_match:
            col1 = table_row_match.group(1).strip()
            col2 = table_row_match.group(2).strip()
            # Skip header if it's generic like "Item" / "Details"
            if col1.lower() in ["item", "field", "feature", "parameter"] and col2.lower() in ["details", "info", "description", "value"]:
                continue
            
            # Format cleanly as bullet point
            clean_col1 = col1.replace("**", "").replace("__", "").strip()
            cleaned_lines.append(f"- **{clean_col1}:** {col2}")
            continue
            
        cleaned_lines.append(line)
        
    s = "\n".join(cleaned_lines)
    
    # 5. Clean up multiple empty lines
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    
    return s
